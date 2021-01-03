import json
from asyncio import Queue
from asyncio import wait as wait_coros
from typing import *

from aiohttp.web import WebSocketResponse

from core import Event, Player


class PlayerManager:
    def __init__(self, players: List[Player]):
        self.players: List[Player] = players
        self.players_sids: Dict[Player, str] = {}
        self.sids_players: Dict[str, Player] = {}
        # sid: session id
        self.sids_sockets: Dict[str, WebSocketResponse] = {}
        # WebSocket 接收信息必须在 request_handler task 中完成，故使用队列中转
        self.sids_queues: Dict[str, Queue] = {}
        self.unregistered_players: List[Player] = self.players.copy()
        # sids_msgs_on_recovery: 重新连接后，需要再次发送的消息
        self.sids_msgs_on_recovery: Dict[str, List[Dict]] = {}

    def register_player(self, sid: str, player: Player, ws: WebSocketResponse) -> Queue:
        if player in self.unregistered_players:
            self.players_sids[player] = sid
            self.sids_players[sid] = player
            self.unregistered_players.remove(player)
            queue = Queue()
            self.sids_queues[sid] = queue
            self.sids_sockets[sid] = ws
            self.sids_msgs_on_recovery[sid] = []
            return queue
        else:
            raise ValueError('Player registered')

    async def reconnect(self, sid: str, ws: WebSocketResponse):
        if not self.sids_sockets[sid].closed:
            raise ValueError(
                'The connection is not lost yet, so cannot reconnect')
        self.sids_sockets[sid] = ws

    async def resend_messages(self, sid: str):
        """
        重新连接后，重新发送未被回答的询问消息（例如，ask_player_action）
        """
        for msg in self.sids_msgs_on_recovery[sid]:
            await self.send_to(sid, msg)
        # self.sids_msgs_on_recovery[sid].clear()

    async def send_to(self, who: Union[Player, str], data: Dict):
        if isinstance(who, Player):
            who = self.players_sids[who]
        ws = self.sids_sockets[who]
        await ws.send_json(data, dumps=json_dumps)

    async def receive_from(self, who: Player) -> Dict:
        if isinstance(who, Player):
            who = self.players_sids[who]
        queue = self.sids_queues[who]
        return await queue.get()

    async def send_to_everyone(self, data: Dict):
        await wait_coros([
            self.send_to(player, data)
            for player in self.players
            if player not in self.unregistered_players
        ])

    async def ask(self, player, data: Dict) -> Dict:
        sid = self.players_sids[player]
        self.sids_msgs_on_recovery[sid].append(data)
        await self.send_to(player, data)
        answer = await self.receive_from(player)
        self.sids_msgs_on_recovery[sid].remove(data)
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
