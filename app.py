import base64
import functools
import json
import logging

import jinja2
from aiohttp import WSMsgType, web
from aiohttp_session import Session, get_session, setup, new_session
from aiohttp_session.cookie_storage import EncryptedCookieStorage
from cryptography import fernet

from game_room import GameRoom
from rsa_util import RsaUtil
from storage import Storage, User, UserValidationError


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


def with_session(request_handler):
    @functools.wraps(request_handler)
    async def wrapper(self, request: web.Request):
        session = await get_session(request)
        return await request_handler(self, request, session)

    return wrapper


def login_required(request_handler):
    @functools.wraps(request_handler)
    async def wrapper(self, request: web.Request, session: Session):
        if not session.get('user', ''):
            raise web.HTTPFound(request.app.router['login'].url_for().with_query({'next': request.url.raw_path_qs}))
        return await request_handler(self, request, session)

    return wrapper


class WallGameApp(web.Application):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.add_routes([
            web.static('/static/', './static/'),
            web.get('/', self.main_handler, name='list_rooms'),
            web.route('*', '/new/', self.new_handler, name='create_room'),
            web.route('*', '/login/', self.login_handler, name='login'),
            web.route('*', '/register/', self.register_handler, name='register'),
            web.route('*', '/edit-profile/', self.edit_profile_handler, name='edit_profile'),
            web.get('/logout/', self.logout_handler, name='logout'),
            web.get('/{room}/', self.room_handler, name='room_page'),
            web.get('/{room}/ws/', self.websocket_handler, name='room_ws'),
        ])

        fernet_key = fernet.Fernet.generate_key()
        secret_key = base64.urlsafe_b64decode(fernet_key)
        setup(self, EncryptedCookieStorage(secret_key))

        self.env = jinja2.Environment(loader=jinja2.FileSystemLoader('./templates'),
                                      autoescape=True)

        self.rsa = RsaUtil()
        self.storage = Storage()

    def render(self, template, /, **kwargs):
        return web.Response(
            body=self.env.get_template(template).render(**kwargs),
            content_type='text/html'
        )

    @with_session
    async def main_handler(self, request: web.Request, session: Session):
        available_rooms = {room for room in GameRoom.instances.values()
                           if room.manager.unregistered_players}
        return self.render('index.html', rooms=available_rooms, session=session)

    @with_session
    @login_required
    async def new_handler(self, request: web.Request, session: Session):
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
                           error_message=error_message, session=session)

    @auto_404
    @with_session
    @login_required
    async def room_handler(self, request: web.Request, session: Session):
        room_id = request.match_info['room']
        try:
            return self.render('room.html', room=GameRoom.instances[room_id], session=session)
        except KeyError:
            raise web.HTTPNotFound()

    @auto_404
    @with_session
    @login_required
    async def websocket_handler(self, request: web.Request, session: Session):
        room_id = request.match_info['room']

        user = session['user']
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        try:
            room = GameRoom.instances[room_id]
        except KeyError:
            await ws.send_json({'event': 'error', 'message': '房间不存在或游戏已结束'})
            await ws.close()
        if user not in room.manager.users_sockets:
            try:
                player = room.manager.unregistered_players[0]
                player.symbol = self.storage.get_user(user).symbol
                queue = await room.register_player(user, player, ws)
            except IndexError:
                await ws.send_json({'event': 'error', 'message': '加入房间失败，可能房间已满！'})
                return
        else:
            logging.info('someone reconnect')
            try:
                await room.reconnect(user, ws)
            except ValueError:
                await ws.send_json({'event': 'error', 'message': '你已进入该房间！'})
                return
            queue = room.manager.users_queues[user]

        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                await queue.put(json.loads(msg.data))

        return web.Response()

    async def login_handler(self, request: web.Request):
        if request.method == 'POST':
            post = await request.post()
            username = post['username']
            password_encrypted = post['password_encrypted']
            password = self.rsa.decrypt_by_private_key(password_encrypted)
            try:
                user = self.storage.get_user(username)
                session = await new_session(request)
                if user.verify_password(password):
                    session['user'] = user.name

                raise web.HTTPFound(request.query.get('next', '/'))
            except ValueError:
                pass
            error_message = '用户名或密码错误'
        else:
            error_message = ''
            username = ''
        return self.render('login.html', username=username, error_message=error_message, session={'user': ''})

    async def register_handler(self, request: web.Request):
        if request.method == 'POST':
            post = await request.post()
            raw_password = self.rsa.decrypt_by_private_key(post['password_encrypted'])
            try:
                user = User(post['username'], post['symbol'], raw_password=raw_password)
                self.storage.new_user(user)
                session = await new_session(request)
                session['user'] = user.name
                session
                self.storage.save()
                raise web.HTTPFound(request.query.get('next', '/'))
            except UserValidationError as exc:
                error_message = exc.args[0]
            username = post['username']
            symbol = post['symbol']
        else:
            username = ''
            symbol = ''
            error_message = ''
        return self.render('register.html', username=username, symbol=symbol,
                           error_message=error_message, session={'user': ''})

    @with_session
    @login_required
    async def edit_profile_handler(self, request: web.Request, session: Session):
        if request.method == 'POST':
            post = await request.post()
            raw_old_password = self.rsa.decrypt_by_private_key(post['old_password_encrypted'])
            user = self.storage.get_user(session['user'])
            if user.verify_password(raw_old_password):
                if post['password_encrypted']:
                    raw_new_password = self.rsa.decrypt_by_private_key(post['password_encrypted'])
                    user.set_password(raw_new_password)
                user.symbol = post['symbol']
                user.name = post['username']
                try:
                    self.storage.update_user(user)
                    self.storage.save()
                    raise web.HTTPFound('/')
                except UserValidationError as exc:
                    error_message = exc.args[0]
            else:
                error_message = '旧密码错误'
            username = post['username']
            symbol = post['symbol']
        else:
            user = self.storage.get_user(session['user'])
            username = user.name
            symbol = user.symbol
            error_message = ''
        return self.render('edit_profile.html', username=username, symbol=symbol,
                           error_message=error_message, session=session)

    @with_session
    @login_required
    async def logout_handler(self, request: web.Request, session: Session):
        session['user'] = ''
        raise web.HTTPFound(self.router['list_rooms'].url_for())
