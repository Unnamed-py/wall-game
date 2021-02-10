import uuid
import enum
from asyncio import Queue, create_task
from typing import *

from aiohttp.web import WebSocketResponse

from core import Direction, Event, Player, WallGame
from player_manager import PlayerManager


class RoomStatus(enum.Enum):
    waiting = 'waiting'
    running = 'running'
    finished = 'finished'


class GameRoom:
    instances: 'Dict[str, GameRoom]' = {}

    @property
    def players(self):
        return self.manager.players

    def __init__(self, size, name, player_positions) -> None:
        self.id: str = str(uuid.uuid1())
        self.name: str = name
        self.instances[self.id] = self
        players = [Player(str(i), row, col) for i, (row, col) in enumerate(player_positions, 1)]
        self.game: WallGame = WallGame(size, players)
        self.manager = PlayerManager(self.game.players)
        self.status: RoomStatus = RoomStatus.waiting
        self.players_initial_poses: Dict[str, Tuple] = {player: (player.row, player.col)
                                                        for player in self.manager.players}
        if len(self.players_initial_poses) != len(self.manager.players):
            raise ValueError('duplicated player_positions')
        self.task = None

    async def register_player(self, sid: str, player: Player, ws: WebSocketResponse) -> Queue:
        queue = self.manager.register_player(sid, player, ws)
        await self.manager.send_to(player, {
            'event': Event.joined, 'player': player.symbol
        })
        await self.manager.send_to_everyone({
            'event': Event.new_player,
            'player': player
        })

        if len(self.manager.unregistered_players) == 0:
            await self.start_game()
        return queue

    async def start_game(self):
        await self.manager.send_to_everyone({'event': Event.game_start})
        self.task = create_task(self.game_loop())

    async def reconnect(self, user: str, ws: WebSocketResponse):
        await self.manager.reconnect(user, ws)
        player = self.manager.users_players[user]
        await self.manager.send_to(user, {
            'event': Event.reconnected,
            'player': player,
            'pos': [player.row, player.col],
            'status': self.status.value
        })
        if self.status != RoomStatus.finished:
            await self.manager.send_to(user, self.update_game_map_message())
        await self.manager.resend_messages(user)

    async def game_loop(self):
        self.status = RoomStatus.running
        loop = self.game.game_loop()
        reply = None
        try:
            while True:
                event, *args = loop.send(reply)
                if event is Event.ask_player_action:
                    player, msg = args
                    data = await self.manager.ask(player, {
                        'event': event,
                        'msg': msg,
                        'reachable_points': [
                            [row, col] for row, col in
                            self.game.get_reachable_points(player)
                        ]
                    })
                    reply = data['motions'], Direction[data['wall_dir']]

                elif event is Event.update_game_map:

                    await self.manager.send_to_everyone(self.update_game_map_message())

                elif event is Event.player_out:
                    player, score = args
                    await self.manager.send_to_everyone({
                        'event': event,
                        'player': player.symbol,
                        'score': score
                    })

        except StopIteration as exc:
            self.status = RoomStatus.finished
            data = [[f'{self.manager.players_users[player]}({player.symbol})', score]
                    for player, score in exc.value.items()]
            data.sort(key=lambda item: item[1], reverse=True)
            # 发送游戏结果并询问是否重新开始
            async for user, reply in self.manager.ask_everyone({
                    'event': Event.game_over,
                    'result': data}):
                if reply.get('agree'):
                    await self.manager.send_to_everyone({'event': Event.agreed_restarting, 'user': user})
                else:
                    await self.manager.send_to_everyone({'event': 'error', 'message': f'由于{user}拒绝重新开始游戏，游戏房间将被销毁'})
                    del self.instances[self.id]
                    return

            # 重新开始
            for player, (row, col) in self.players_initial_poses.items():
                player.row = row
                player.col = col
            self.game.__init__(self.game.size, self.game.players)
            await self.start_game()

    def update_game_map_message(self):
        wall_top = [''.join('1' if char else '0' for char in row)
                    for row in self.game.wall_top]
        wall_left = [''.join('1' if char else '0' for char in row)
                     for row in self.game.wall_left]
        players_info = [(player.row, player.col, player.symbol)
                        for player in self.game.players]
        return {
            'event': Event.update_game_map,
            'wall_top': wall_top,
            'wall_left': wall_left,
            'players_info': players_info
        }
