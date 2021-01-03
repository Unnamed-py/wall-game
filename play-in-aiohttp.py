import logging
from aiohttp import web
from app import WallGameApp

logging.basicConfig(level=logging.INFO)
app = WallGameApp()
web.run_app(app)
