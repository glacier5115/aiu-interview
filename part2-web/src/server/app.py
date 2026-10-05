"""FastAPI 应用装配。

只做装配：把接口路由和前端静态页面挂到同一个应用上。
由于前端页面由同一个服务提供，前后端同源，因此不需要额外配置 CORS。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shared.llm_chat.client import OllamaClient
from shared.vision.detector import Detector

from . import routes
from .sessions import SessionStore

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(
    client: OllamaClient,
    store: SessionStore,
    detector: Detector | None = None,
) -> FastAPI:
    """组装应用。

    依赖由调用方（main.py）注入并挂到 ``app.state``，路由按需取用，
    这样路由层不需要关心它们是怎么构造出来的。

    detector 允许为 None：没装 ultralytics、没有训练好的权重、或者显存不够时，
    对话功能照常可用，只是检测接口会返回明确的错误。
    """
    app = FastAPI(
        title="本地大模型 Web 服务",
        description="通过 Ollama 接入本地模型（SSE 流式输出），并提供 YOLO 目标检测接口",
        version="0.2.0",
    )
    app.state.client = client
    app.state.store = store
    app.state.detector = detector

    # 接口优先注册；静态页面挂在最后，作为兜底处理其余路径
    app.include_router(routes.router)
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

    return app
