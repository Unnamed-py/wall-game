import asyncio
import base64
import functools
import json
import logging
import traceback
import uuid
from asyncio.queues import Queue
from typing import *

import jinja2
from aiohttp import WSMsgType, web
from aiohttp.web_ws import WebSocketResponse
from aiohttp_session import Session, get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet

from core import Direction, Event, Player, WallGame


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

    async def register_player(self, sid: str, player: Player, ws: web.WebSocketResponse) -> Queue:
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
            self.task = asyncio.create_task(self.game_loop())
        return queue

    async def reconnect(self, sid: str, ws: web.WebSocketResponse):
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
        await asyncio.wait([
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


def render(template, /, **kwargs):
    return web.Response(
        body=env.get_template(template).render(**kwargs),
        content_type='text/html'
    )


def auto_404(request_handler):
    """
    raise HTTPNotFound if a LookupError is occurred
    so that the client will get a 404 instead of 500
    """
    @functools.wraps(request_handler)
    async def wrapper(*args, **kwargs):
        try:
            return await request_handler(*args, **kwargs)
        except LookupError:
            raise web.HTTPNotFound
    return wrapper


routes = web.RouteTableDef()
routes.static('/static', './static')


@routes.get('/')
async def main_handler(request: web.Request):
    available_rooms = {room for room in GameRoom.instances.values()
                       if room.manager.unregistered_players}
    return render('index.html', rooms=available_rooms)


@routes.route('*', '/new/')
async def new_handler(request: web.Request):
    if request.method == 'POST':
        post_data = await request.post()
        name = post_data.get('name')
        size = post_data.get('size')
        try:
            size = int(size)
            if 2 <= size <= 20 and name.strip():
                room = GameRoom(size, name)
            else:
                raise ValueError()
        except ValueError:
            error_message = '名称 必须非空，2 <= 尺寸 <= 20'
        else:
            raise web.HTTPFound(f'/{room.id}/')
    else:
        name = ''
        size = 7
        error_message = ''
    return render('new.html', name=name, size=size,
                  error_message=error_message)


@routes.get(r'/{room}/')
@auto_404
async def room_handler(request: web.Request):
    session = await get_session(request)
    session.setdefault('sid', str(uuid.uuid1()))
    room_id = request.match_info['room']
    try:
        return render('room.html', room=GameRoom.instances[room_id])
    except KeyError:
        raise web.HTTPNotFound()


@routes.get(r'/{room}/ws/')
@auto_404
async def websocket_handler(request: web.Request):
    room_id = request.match_info['room']
    room = GameRoom.instances[room_id]
    sessoin = await get_session(request)
    sid = sessoin['sid']
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    if sid not in room.manager.sids_sockets:
        try:
            queue = await room.register_player(sid, room.manager.unregistered_players[0], ws)
        except ValueError:
            await ws.send_json({'event': 'error', 'message': '加入房间失败，可能房间已满！'})
            return
    else:
        logging.info('someone reconnect')
        try:
            await room.reconnect(sid, ws)
        except ValueError:
            await ws.send_json({'event': 'error', 'message': '你已进入该房间！'})
            return
        queue = room.manager.sids_queues[sid]

    async for msg in ws:
        if msg.type == WSMsgType.TEXT:
            await queue.put(json.loads(msg.data))

    return web.Response()


logging.basicConfig(level=logging.INFO)
env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('./templates'),
    autoescape=True
)
app = web.Application()
fernet_key = fernet.Fernet.generate_key()
secret_key = base64.urlsafe_b64decode(fernet_key)
setup(app, EncryptedCookieStorage(secret_key))
app.add_routes(routes)
web.run_app(app)
