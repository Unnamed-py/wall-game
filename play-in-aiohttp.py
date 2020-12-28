from typing import *
import asyncio
import traceback
import uuid
import json
import aiohttp
from aiohttp.tracing import TraceRequestExceptionParams

import jinja2
from aiohttp import web

import core


class GameRoom:
    instances: 'Dict[str, GameRoom]' = {}

    def __init__(self, size, name, players=None) -> None:
        self.id: str = str(uuid.uuid1())
        self.name: str = name
        self.instances[self.id] = self
        self.game: core.WallGame = core.WallGame(size, players)
        self.player_socks: Dict[core.Player, web.WebSocketResponse] = {}
        self.sock_players: Dict[web.WebSocketResponse, core.Player] = {}
        # WebSocket 接收信息必须在 request_handler task 中完成，故使用队列中转
        self.player_queues: Dict[core.Player, asyncio.Queue] = {}
        self.players_without_sock: List[core.Player] = self.game.players.copy()

        self.task = None

    async def add_player(self, player: core.Player, sock: web.WebSocketResponse, queue: asyncio.Queue):
        if player in self.players_without_sock:
            futures = [sock.send_json({'event': 'new_player', 'player': player.symbol})
                       for sock in self.sock_players]
            if futures:
                await asyncio.wait(futures)
            self.player_socks[player] = sock
            self.sock_players[sock] = player
            self.player_queues[player] = queue
            self.players_without_sock.remove(player)
            if len(self.players_without_sock) == 0:
                await asyncio.wait([sock.send_json({'event': 'game_start'})
                                    for sock in self.sock_players])
                self.task = asyncio.create_task(self.game_loop())
        else:
            raise ValueError

    async def game_loop(self):
        print('Running game loop...')
        loop = self.game.game_loop()
        reply = None
        try:
            while True:
                event, *args = loop.send(reply)
                if event is core.Event.ask_player_action:
                    player, msg = args
                    ws = self.player_socks[player]
                    queue = self.player_queues[player]

                    await ws.send_json({
                        'event': event.name,
                        'msg': msg,
                        'reachable_points': [
                            [row, col] for row, col in
                            self.game.get_reachable_points(player)
                        ]
                    })
                    data = await queue.get()
                    reply = data['motions'], data['wall_dir']

                elif event is core.Event.update_game_map:
                    wall_top = [''.join('1' if char else '0' for char in row)
                                for row in self.game.wall_top]
                    wall_left = [''.join('1' if char else '0' for char in row)
                                 for row in self.game.wall_left]
                    players_info = [[player.row, player.col, player.symbol]
                                    for player in self.game.players]

                    await asyncio.wait([asyncio.create_task(sock.send_json({
                        'event': event.name,
                        'wall_top': wall_top,
                        'wall_left': wall_left,
                        'players_info': players_info
                    })) for sock in self.sock_players])

                elif event is core.Event.player_out:
                    player, score = args
                    await asyncio.wait([asyncio.create_task(sock.send_json({
                        'event': event.name,
                        'player': player.symbol,
                        'score': score
                    })) for sock in self.sock_players])

        except StopIteration as exc:
            data = [[player.name, score] for player, score in exc.value]
            data.sort(key=lambda item: item[1], reverse=True)
            await asyncio.wait([asyncio.create_task(sock.send_json({
                'event': 'game_over',
                'result': data
            })) for sock in self.sock_players])
            del self.instances[self.id]


routes = web.RouteTableDef()
routes.static('/static', './static')


@routes.get('/')
async def main_handler(request: web.Request):
    available_rooms = {room for room in GameRoom.instances.values()
                       if room.players_without_sock}
    return web.Response(body=env.get_template('index.html').render(rooms=available_rooms), content_type='text/html')


@routes.route('*', '/new/')
async def new_handler(request: web.Request):
    if request.method == 'POST':
        post_data = (await request.post())
        name = post_data.get('name')
        size = post_data.get('size')
        try:
            size = int(size)
            if 2 <= size <= 20 and name.strip():
                room = GameRoom(size, name)
            else:
                raise ValueError()
        except ValueError:
            error_message = 'name 必须非空，2 <= size <= 20'
        else:
            raise web.HTTPFound(f'/{room.id}/')
    else:
        name = ''
        size = 7
        error_message = ''
    return web.Response(body=env.get_template('new.html').render(name=name, size=size, error_message=error_message), content_type='text/html')


@routes.get(r'/{room}/')
async def room_handler(request: web.Request):
    room_id = request.match_info['room']
    try:
        return web.Response(body=env.get_template('room.html').render(room=GameRoom.instances[room_id]), content_type='text/html')
    except KeyError:
        raise web.HTTPNotFound()


@routes.get(r'/{room}/ws/')
async def websocket_handler(request: web.Request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    room_id = request.match_info['room']
    room = GameRoom.instances[room_id]
    queue = asyncio.Queue()
    try:
        await room.add_player(room.players_without_sock[0], ws, queue)
    except ValueError:
        traceback.print_exc()
        await ws.send_json({
            'event': 'joined',
            'successful': False
        })
        await ws.close()
    else:
        await ws.send_json({
            'event': 'joined',
            'successful': True,
            'player': room.sock_players[ws].symbol
        })
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.TEXT:
                await queue.put(json.loads(msg.data))


env = jinja2.Environment(
    loader=jinja2.FileSystemLoader('./templates'),
    autoescape=True
)
app = web.Application()
app.add_routes(routes)
web.run_app(app)
