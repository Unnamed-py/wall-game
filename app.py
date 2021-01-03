import asyncio
import base64
import functools
import json
import logging
import traceback
import uuid
from asyncio.queues import Queue
from typing import *
from aiohttp.web_routedef import static

import jinja2
from aiohttp import WSMsgType, web
from aiohttp_session import Session, get_session, setup
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from aiohttp_auth import auth
from cryptography import fernet

# from storage import Storage
from game_room import GameRoom


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


class WallGameApp(web.Application):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)

        self.add_routes((web.static('/static/', './static/'),
                         web.get('/', self.main_handler)),
                        web.route('*', '/new/', self.new_handler),
                        web.get('/{room}/', self.room_handler),
                        web.get('/{room}/ws/', self.websocket_handler))

        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self, EncryptedCookieStorage(secret_key))

        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader('./templates'),
                                      autoescape=True)

    def render(self, template, /, **kwargs):
        return web.Response(
            body=self.env.get_template(template).render(**kwargs),
            content_type='text/html'
        )

    async def main_handler(self, request: web.Request):
        available_rooms = {room for room in GameRoom.instances.values()
                           if room.manager.unregistered_players}
        return self.render('index.html', rooms=available_rooms)

    async def new_handler(self, request: web.Request):
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
        return self.render('new.html', name=name, size=size,
                           error_message=error_message)

    @auto_404
    async def room_handler(self, request: web.Request):
        session = await get_session(request)
        session.setdefault('sid', str(uuid.uuid1()))
        room_id = request.match_info['room']
        try:
            return self.render('room.html', room=GameRoom.instances[room_id])
        except KeyError:
            raise web.HTTPNotFound()

    @auto_404
    async def websocket_handler(self, request: web.Request):
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
