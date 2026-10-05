"""FastAPI 应用装配。

只做装配：接口路由 + 前端静态页面挂在同一个应用上。前端由同一个服务提供，
所以前后端同源，不需要配置 CORS。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shared.llm_chat.client import OllamaClient

from . import routes
from .games import GameStore

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(client: OllamaClient, store: GameStore) -> FastAPI:
    """组装应用。

    依赖由调用方（main.py）注入并挂到 ``app.state``，路由按需取用。
    """
    app = FastAPI(
        title="AI GM 跑团",
        description="本地大模型当游戏主持人，掷骰与规则裁定由程序负责",
        version="0.1.0",
    )
    app.state.client = client
    app.state.store = store

    app.include_router(routes.router)
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
