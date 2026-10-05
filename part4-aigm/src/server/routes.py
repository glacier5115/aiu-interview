"""HTTP 接口。

前端只发两种请求：开一局、走一步。所有规则判定都在 ``aigm`` 包里，这里只做
参数校验和结果序列化——Web 层不该有任何一行跟骰子或角色数值有关的逻辑。

推进回合的路由写成**同步函数**：调模型是阻塞的，写成 async 会卡住事件循环。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from shared.llm_chat.client import OllamaError

from aigm.character import BACKGROUNDS
from aigm.config import SAVES_DIR
from aigm.gamestate import GameState
from aigm.gm import GameError, complete_persona, complete_world
from aigm.rules import ATTRIBUTES, ATTRIBUTE_MAX, ATTRIBUTE_MIN, ATTRIBUTE_POINTS
from aigm.worlds import PRESETS, TONES

from .games import Game, GameStore

router = APIRouter(prefix="/api")


def _sse(payload: dict) -> str:
    """把一条事件编码成 SSE 报文。

    ``ensure_ascii=False`` 让中文按 UTF-8 直接输出，不转成 ``\\uXXXX``。
    """
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


class NewGameRequest(BaseModel):
    """开局的参数。"""

    name: str = Field(default="无名者", max_length=20, description="角色名")
    background: str = Field(
        default="行者", max_length=16, description="身份；选自定义时这里是玩家自己填的名字"
    )
    world: dict | str | None = Field(
        default=None,
        description="世界观：可以传预置世界的名字，也可以传一整份自定义或生成的内容",
    )
    attributes: dict[str, int] | None = Field(
        default=None, description="自定义属性分配。不传则用该身份的推荐值"
    )
    persona_fields: dict[str, str] | None = Field(
        default=None, description="玩家填好的人设字段（可能含 AI 补全后的结果）"
    )
    complete_persona: bool = Field(
        default=True, description="是否让 GM 补全空缺。玩家确认过预览时传 False"
    )


class WorldRequest(BaseModel):
    """生成世界观的请求体。同样只生成，不建游戏。"""

    keywords: str = Field(default="", max_length=200, description="关键词，留空则自由发挥")
    name: str = Field(default="", max_length=16, description="世界名，可留空")
    tone: str = Field(default="", max_length=8, description="基调，可留空")


class PersonaRequest(BaseModel):
    """生成人设的请求体。只生成，不建游戏，供开局界面预览和重新生成。"""

    name: str = Field(default="无名者", max_length=20)
    background: str = Field(default="行者", max_length=16)
    fields: dict[str, str] = Field(default_factory=dict, description="玩家已经填好的字段")
    attributes: dict[str, int] | None = Field(default=None, description="玩家已分配的属性")


class TurnRequest(BaseModel):
    """一个回合的请求体。"""

    game_id: str = Field(..., min_length=1, max_length=64)
    action: str = Field(..., min_length=1, max_length=500, description="玩家这一轮的行动")


class GameRef(BaseModel):
    """只带 game_id 的请求体。"""

    game_id: str = Field(..., min_length=1, max_length=64)


class SaveFileRef(BaseModel):
    """指向一个存档文件。"""

    file: str = Field(..., min_length=1, max_length=200, description="存档文件名")


def _snapshot(game: Game) -> dict:
    """给前端的一局快照。

    连同全部回合记录一起返回：跑团一局也就几十轮，一次给全比让前端自己
    拼接历史要简单可靠。
    """
    state = game.state
    return {
        "id": state.id,
        "scenario": state.scenario,  # 就是 world.name，留给旧前端
        "world": state.world.to_dict(),
        "opening": state.opening,
        "turn_count": state.turn_count,
        "over": state.over,
        "summary": state.summary,
        "character": state.character.to_dict(),
        "scene": state.scene,
        # 给前端的人物卡：不含秘密字段
        "npcs": [npc.to_dict() for npc in state.npcs],
        "facts": list(state.facts),
        "turns": [turn.to_dict() for turn in state.turns],
    }


def _require_game(request: Request, game_id: str) -> Game:
    store: GameStore = request.app.state.store
    try:
        return store.require(game_id)
    except KeyError:
        raise HTTPException(
            status_code=404, detail="找不到这一局游戏，可能服务重启过，请重新开局"
        ) from None


@router.get("/health")
def health(request: Request) -> dict:
    """服务状态。"""
    store: GameStore = request.app.state.store
    client = request.app.state.client
    reachable = client.ping()
    return {
        "ok": reachable,
        "model": client.model,
        "ollama_host": client.host,
        "models": client.list_models() if reachable else [],
        "games": store.count(),
    }


@router.get("/options")
def options() -> dict:
    """开局表单需要的选项。

    前端完全按这份数据渲染表单：身份选项、剧本、属性规则、人设字段。
    以后加身份或调点数，只改后端这一处。
    """
    return {
        "identities": [
            {"name": name, "attributes": attributes}
            for name, attributes in BACKGROUNDS.items()
        ],
        "worlds": [
            {
                "name": world.name,
                "pitch": world.pitch,
                "tone": world.tone,
                "details": world.details,
                "origin": world.origin,
            }
            for world in PRESETS
        ],
        "tones": list(TONES),
        "attribute_points": ATTRIBUTE_POINTS,
        "attribute_range": [ATTRIBUTE_MIN, ATTRIBUTE_MAX],
        "attribute_names": list(ATTRIBUTES),
        "persona_fields": [
            {"key": "appearance", "label": "外貌", "hint": "一句话，最好带个具体细节"},
            {"key": "personality", "label": "性格", "hint": "一句话，别写评价词"},
            {"key": "motivation", "label": "目标", "hint": "他想要什么"},
            {"key": "background", "label": "来历", "hint": "两三句话"},
            {"key": "trait", "label": "特质", "hint": "能影响行为的那种，比如「怕火」"},
        ],
    }


@router.post("/persona/generate")
def generate_persona(payload: PersonaRequest, request: Request) -> dict:
    """生成或补全人设，不建游戏。

    单独开一个接口，是为了让开局界面能「生成 → 看看 → 不满意再生成」。
    如果把它绑在开局流程里，玩家就只能先进游戏再退出来重来。
    """
    try:
        data = complete_persona(
            request.app.state.client,
            payload.name,
            payload.background,
            payload.fields,
            payload.attributes,
        )
    except (OllamaError, GameError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "persona": data}


@router.post("/world/generate")
def generate_world(payload: WorldRequest, request: Request) -> dict:
    """生成一份世界观。和 /persona/generate 一样，只生成，不建游戏。"""
    try:
        world = complete_world(
            request.app.state.client, payload.keywords, payload.name, payload.tone
        )
    except (OllamaError, GameError) as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {"ok": True, "world": world.to_dict()}


@router.post("/game/new")
def new_game(payload: NewGameRequest, request: Request) -> dict:
    """开一局新的，并让 GM 生成开场。"""
    store: GameStore = request.app.state.store
    # world 允许传名字，也允许传一整份内容，由 worlds.to_world 统一处理
    game = store.create(
        payload.name, payload.background, payload.world, payload.attributes
    )

    # 人设：玩家确认过预览就直接用，否则让 GM 补全。
    # 两条路失败都不拦开局——最多是角色少一份设定。
    fields = dict(payload.persona_fields or {})
    try:
        if payload.complete_persona:
            data = complete_persona(
                request.app.state.client,
                payload.name,
                payload.background,
                fields,
                game.state.character.attributes,
            )
        else:
            data = fields
        game.engine.apply_persona(data)
    except (OllamaError, GameError):
        pass

    # 关键人物丢到**后台**生成，不占开局的等待时间。
    #
    # 试过把它们并进开局：先是想省一次调用，结果开局从三十秒涨到五十八秒——耗时
    # 的大头是模型要吐多少 token，少一次调用根本省不下来，提示词一长反而更慢。
    # 挪到后台之后开局回到三十秒上下，玩家读完开场那几十个字，人物差不多也就位了。
    threading.Thread(
        target=store.warm_npcs, args=(game,), daemon=True, name=f"npcs-{game.id}"
    ).start()

    try:
        # 开场存进状态里，这样存档时一起保存，读档回来还能看到
        game.state.opening = game.engine.opening()
    except OllamaError as exc:
        store.drop(game.id)  # 开场都生成不了，这一局留着也没用
        raise HTTPException(status_code=502, detail=f"GM 没能开场：{exc}") from exc

    return {"ok": True, "game": _snapshot(game)}


@router.post("/game/turn")
def play_turn(payload: TurnRequest, request: Request) -> StreamingResponse:
    """推进一个回合，以 SSE 流式返回。

    流式不只是为了好看：模型写一段叙事要十几秒，等它全写完再一次性返回的话，
    玩家只能盯着转圈的图标。现在文字是边生成边出来的。
    """
    store: GameStore = request.app.state.store
    game = _require_game(request, payload.game_id)

    return StreamingResponse(
        _turn_events(store, game, payload.action),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _turn_events(store: GameStore, game: Game, action: str):
    """把一回合拆成 SSE 事件流。

    同步生成器：Starlette 会把它放到线程池里迭代，所以内部阻塞式的模型读取
    不会卡住事件循环。前端断开时整个生成器会被关闭，``play_stream`` 里的
    finally 会把未提交的改动退回去。
    """
    try:
        for event in store.play_stream(game, action):
            if event["type"] == "done":
                yield _sse({"type": "done", "game": _snapshot(game)})
            else:
                yield _sse(event)
    except GameError as exc:
        yield _sse({"type": "error", "message": str(exc)})
    except OllamaError as exc:
        yield _sse({"type": "error", "message": f"GM 没有回应：{exc}"})
    except Exception as exc:  # noqa: BLE001  兜底：任何意外都要让前端知道
        yield _sse({"type": "error", "message": f"回合异常终止：{exc}"})


@router.post("/game/state")
def game_state(payload: GameRef, request: Request) -> dict:
    """取一局的当前状态。页面刷新后用它把进度接回来。"""
    game = _require_game(request, payload.game_id)
    return {"ok": True, "game": _snapshot(game)}


@router.post("/game/save")
def save_game(payload: GameRef, request: Request) -> dict:
    """把当前进度写进存档目录。"""
    game = _require_game(request, payload.game_id)
    path = game.state.save()
    return {"ok": True, "file": path.name, "turn_count": game.state.turn_count}


@router.get("/saves")
def list_saves() -> dict:
    """列出已有存档。"""
    return {"ok": True, "saves": GameState.list_saves()}


def _safe_save_path(name: str) -> Path:
    """把存档名解析成存档目录内的路径。

    文件名来自前端，必须防一手路径穿越（`../../something`）。这里只取最后一段
    文件名，再校验它确实落在存档目录里。
    """
    root = SAVES_DIR.resolve()
    candidate = (root / Path(name).name).resolve()
    if candidate.parent != root or candidate.suffix != ".json":
        raise HTTPException(status_code=400, detail="非法的存档名")
    return candidate


@router.post("/game/load")
def load_game(payload: SaveFileRef, request: Request) -> dict:
    """从存档恢复一局，接着玩。"""
    store: GameStore = request.app.state.store
    path = _safe_save_path(payload.file)
    if not path.exists():
        raise HTTPException(status_code=404, detail="找不到这个存档")

    try:
        state = GameState.load(path)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(status_code=400, detail=f"存档读不出来：{exc}") from exc

    game = store.adopt(state)
    return {"ok": True, "game": _snapshot(game)}


@router.post("/game/delete")
def delete_save(payload: SaveFileRef) -> dict:
    """删除一个存档文件。"""
    path = _safe_save_path(payload.file)
    if not path.exists():
        raise HTTPException(status_code=404, detail="找不到这个存档")
    path.unlink()
    return {"ok": True, "file": payload.file}
