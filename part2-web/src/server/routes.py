"""HTTP 接口定义。

后端在这里只做两件事：调用模型算结果、把结果推给前端。
接口返回的是结构化的数据事件，不含任何 HTML 片段或展示逻辑——
怎么显示由前端自己决定。
"""

from __future__ import annotations

import json
import threading

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shared.llm_chat.client import OllamaClient, OllamaError

from .sessions import SessionStore

router = APIRouter(prefix="/api")

# 本地单人使用：一把锁保证同一时刻只有一轮对话在进行，避免上下文交叉
_CHAT_LOCK = threading.Lock()


class ChatRequest(BaseModel):
    """一轮对话的请求体。"""

    message: str = Field(..., min_length=1, description="用户这一轮说的话")
    session_id: str = Field(
        default="default",
        min_length=1,
        max_length=128,
        description="会话标识，由前端生成并保存，后端据此找回上下文",
    )


class SessionAction(BaseModel):
    """会话操作请求体。"""

    session_id: str = Field(default="default", min_length=1, max_length=128)


def _sse(payload: dict) -> str:
    """把一条事件编码成 SSE 报文。

    ensure_ascii=False 让中文按 UTF-8 直接输出，不转成 \\uXXXX。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _chat_events(
    client: OllamaClient,
    store: SessionStore,
    session_id: str,
    message: str,
):
    """把一轮对话拆成事件流。

    这是一个同步生成器：Starlette 会把它放到线程池里迭代，因此内部
    阻塞式的 requests 读取不会卡住事件循环。
    """
    session = store.get(session_id)
    session.add_user(message)

    pieces: list[str] = []
    try:
        with _CHAT_LOCK:
            for piece in client.chat_stream(session.messages):
                pieces.append(piece)
                yield _sse({"type": "delta", "content": piece})
    except OllamaError as exc:
        # 这一轮失败，回滚提问，避免半截内容留在上下文里
        session.drop_last()
        yield _sse({"type": "error", "message": str(exc)})
        return
    except GeneratorExit:
        # 前端主动断开连接，同样回滚
        session.drop_last()
        raise

    if not pieces:
        session.drop_last()
        yield _sse(
            {
                "type": "error",
                "message": "模型没有返回正文。可能是思考内容占满了输出配额。",
            }
        )
        return

    session.add_assistant("".join(pieces))
    yield _sse({"type": "done"})


@router.get("/health")
async def health(request: Request) -> dict:
    """服务状态：供前端显示连接情况，也方便部署后自检。"""
    client: OllamaClient = request.app.state.client
    store: SessionStore = request.app.state.store
    reachable = client.ping()
    return {
        "ok": reachable,
        "ollama_host": client.host,
        "model": client.model,
        "sessions": store.count(),
        "models": client.list_models() if reachable else [],
    }


@router.post("/chat")
async def chat(payload: ChatRequest, request: Request) -> StreamingResponse:
    """发起一轮对话，以 SSE 流式返回模型的输出。"""
    client: OllamaClient = request.app.state.client
    store: SessionStore = request.app.state.store

    return StreamingResponse(
        _chat_events(client, store, payload.session_id, payload.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # 避免中间层（例如反向代理）缓冲流式响应
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/session/reset")
async def reset_session(payload: SessionAction, request: Request) -> dict:
    """清空指定会话的上下文。"""
    store: SessionStore = request.app.state.store
    store.reset(payload.session_id)
    return {"ok": True, "session_id": payload.session_id}
