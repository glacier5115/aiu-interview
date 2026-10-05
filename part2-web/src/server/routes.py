"""HTTP 接口定义。

后端在这里只做两件事：调用模型算结果、把结果推给前端。
接口返回的是结构化的数据事件，不含任何 HTML 片段或展示逻辑——
怎么显示由前端自己决定。
"""

from __future__ import annotations

import io
import json
import threading

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from shared.llm_chat.client import OllamaClient, OllamaError
from shared.vision.detector import Detector

from .sessions import SessionStore

router = APIRouter(prefix="/api")

# 本地单人使用：一把锁保证同一时刻只有一轮对话在进行，避免上下文交叉
_CHAT_LOCK = threading.Lock()

# 上传图片的大小上限，避免一张超大图把内存吃满
MAX_UPLOAD_BYTES = 10 * 1024 * 1024


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
    detector: Detector | None = getattr(request.app.state, "detector", None)
    return {
        "ok": reachable,
        "ollama_host": client.host,
        "model": client.model,
        "sessions": store.count(),
        "models": client.list_models() if reachable else [],
        "vision": {
            "ready": bool(detector and detector.ready),
            "model": detector.weights.name if detector else "",
        },
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


@router.post("/detect")
def detect(request: Request, file: UploadFile = File(...)) -> dict:
    """对上传的图片做目标检测，返回结构化的检测框。

    返回的是**数据**而不是画好的图：前端拿到每个框的坐标、类别和置信度后自己
    叠在图片上，框的样式、悬停效果都由前端决定。

    这个函数刻意不加 async：GPU 推理是阻塞调用，写成同步函数后 FastAPI 会把它
    放到线程池里执行，不会卡住事件循环。
    """
    detector: Detector | None = getattr(request.app.state, "detector", None)
    if detector is None:
        raise HTTPException(
            status_code=503,
            detail="检测模型未就绪：请先在 part3-yolo 目录下训练一次生成权重",
        )

    raw = file.file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="上传的文件是空的")
    if len(raw) > MAX_UPLOAD_BYTES:
        limit = MAX_UPLOAD_BYTES // 1024 // 1024
        raise HTTPException(status_code=413, detail=f"图片过大，上限 {limit} MB")

    try:
        image = Image.open(io.BytesIO(raw))
        image.load()  # 真正解码一次，坏图在这里就会暴露
    except UnidentifiedImageError:
        # PIL 认不出的格式：给一句人看得懂的话，别把内部对象表示抛给用户
        raise HTTPException(
            status_code=400, detail="无法识别这张图片，请确认是 JPG 或 PNG 格式"
        ) from None
    except Exception as exc:  # noqa: BLE001  PIL 的异常类型很杂，统一转成 400
        raise HTTPException(status_code=400, detail=f"无法解析这张图片：{exc}") from exc

    try:
        result = detector.detect(image)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"检测失败：{exc}") from exc

    return {"ok": True, "filename": file.filename or "", **result.to_dict()}
