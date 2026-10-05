"""FastAPI 应用装配。

只做装配：把接口路由和前端静态页面挂到同一个应用上。
由于前端页面由同一个服务提供，前后端同源，因此不需要额外配置 CORS。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shared.llm_chat.client import OllamaClient

from . import routes
from .sessions import SessionStore

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(client: OllamaClient, store: SessionStore) -> FastAPI:
    """组装应用。

    依赖由调用方（main.py）注入并挂到 ``app.state``，路由按需取用，
    这样路由层不需要关心客户端是怎么构造出来的。
    """
    app = FastAPI(
        title="本地大模型 Web 对话服务",
        description="通过 Ollama 接入本地模型，以 SSE 向前端推送输出",
        version="0.1.0",
    )
    app.state.client = client
    app.state.store = store

    # 接口优先注册；静态页面挂在最后，作为兜底处理其余路径
    app.include_router(routes.router)
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
