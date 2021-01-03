from aiohttp import web
from app import WallGameApp

app = WallGameApp()
web.run_app(app)
