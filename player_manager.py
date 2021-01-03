import json
from asyncio import Queue
from asyncio import wait as wait_coros
from typing import *

from aiohttp.web import WebSocketResponse

from core import Event, Player


class PlayerManager:
    def __init__(self, players: List[Player]):
        self.players: List[Player] = players
        self.players_users: Dict[Player, str] = {}
        self.users_players: Dict[str, Player] = {}
        self.users_sockets: Dict[str, WebSocketResponse] = {}
        # WebSocket 接收信息必须在 request_handler task 中完成，故使用队列中转
        self.users_queues: Dict[str, Queue] = {}
        self.unregistered_players: List[Player] = self.players.copy()
        # users_msgs_on_recovery: 重新连接后，需要再次发送的消息
        self.users_msgs_on_recovery: Dict[str, List[Dict]] = {}

    def register_player(self, user: str, player: Player, ws: WebSocketResponse) -> Queue:
        if player in self.unregistered_players:
            self.players_users[player] = user
            self.users_players[user] = player
            self.unregistered_players.remove(player)
            queue = Queue()
            self.users_queues[user] = queue
            self.users_sockets[user] = ws
            self.users_msgs_on_recovery[user] = []
            return queue
        else:
            raise ValueError('Player registered')

    async def reconnect(self, user: str, ws: WebSocketResponse):
        if not self.users_sockets[user].closed:
            raise ValueError(
                'The connection is not lost yet, so cannot reconnect')
        self.users_sockets[user] = ws

    async def resend_messages(self, user: str):
        """
        重新连接后，重新发送未被回答的询问消息（例如，ask_player_action）
        """
        for msg in self.users_msgs_on_recovery[user]:
            await self.send_to(user, msg)

    async def send_to(self, who: Union[Player, str], data: Dict):
        if isinstance(who, Player):
            who = self.players_users[who]
        ws = self.users_sockets[who]
        await ws.send_json(data, dumps=json_dumps)

    async def receive_from(self, who: Player) -> Dict:
        if isinstance(who, Player):
            who = self.players_users[who]
        queue = self.users_queues[who]
        return await queue.get()

    async def send_to_everyone(self, data: Dict):
        await wait_coros([
            self.send_to(player, data)
            for player in self.players
            if player not in self.unregistered_players
        ])

    async def ask(self, player, data: Dict) -> Dict:
        user = self.players_users[player]
        self.users_msgs_on_recovery[user].append(data)
        await self.send_to(player, data)
        answer = await self.receive_from(player)
        self.users_msgs_on_recovery[user].remove(data)
        return answer


class CustomJsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Event):
            obj = obj.value
        elif isinstance(obj, Player):
            obj = obj.symbol
        return obj


def json_dumps(*args, **kwargs):
    kwargs['cls'] = CustomJsonEncoder
    return json.dumps(*args, **kwargs)
