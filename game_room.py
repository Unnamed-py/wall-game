import uuid
from asyncio import Queue, create_task
from typing import *

from aiohttp.web import WebSocketResponse

from core import Direction, Event, Player, WallGame
from player_manager import PlayerManager


class GameRoom:
    instances: 'Dict[str, GameRoom]' = {}

    @property
    def players(self):
        return self.manager.players

    def __init__(self, size, name, players=None) -> None:
        self.id: str = str(uuid.uuid1())
        self.name: str = name
        self.instances[self.id] = self
        self.game: WallGame = WallGame(size, players)
        self.manager = PlayerManager(self.game.players)

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
            await self.manager.send_to_everyone({'event': Event.game_start})
            self.task = create_task(self.game_loop())
        return queue

    async def reconnect(self, sid: str, ws: WebSocketResponse):
        await self.manager.reconnect(sid, ws)
        player = self.manager.sids_players[sid]
        await self.manager.send_to(sid, {
            'event': Event.reconnected,
            'player': player,
            'pos': [player.row, player.col]
        })
        await self.manager.send_to(sid, self.update_game_map_message())
        await self.manager.resend_messages(sid)

    async def game_loop(self):
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
            data = [[player.symbol, score]
                    for player, score in exc.value.items()]
            data.sort(key=lambda item: item[1], reverse=True)
            await self.manager.send_to_everyone({
                'event': Event.game_over,
                'result': data
            })
            del self.instances[self.id]

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
