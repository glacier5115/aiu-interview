"""HTTP 接口。

前端只发两种请求：开一局、走一步。所有规则判定都在 ``aigm`` 包里，这里只做
参数校验和结果序列化——Web 层不该有任何一行跟骰子或角色数值有关的逻辑。

推进回合的路由写成**同步函数**：调模型是阻塞的，写成 async 会卡住事件循环。
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from shared.llm_chat.client import OllamaError

from aigm.character import BACKGROUNDS
from aigm.gm import GameError

from .games import Game, GameStore

router = APIRouter(prefix="/api")

# 开局时可以直接挑的剧本
SCENARIOS = (
    "雾中的旧磨坊",
    "沉没的灯塔",
    "荒废的驿站",
)


class NewGameRequest(BaseModel):
    """开局的参数。"""

    name: str = Field(default="无名者", max_length=20, description="角色名")
    background: str = Field(default="行者", description="出身，决定初始属性")
    scenario: str = Field(default="雾中的旧磨坊", max_length=40, description="剧本名")


class TurnRequest(BaseModel):
    """一个回合的请求体。"""

    game_id: str = Field(..., min_length=1, max_length=64)
    action: str = Field(..., min_length=1, max_length=500, description="玩家这一轮的行动")


class GameRef(BaseModel):
    """只带 game_id 的请求体。"""

    game_id: str = Field(..., min_length=1, max_length=64)


def _snapshot(game: Game) -> dict:
    """给前端的一局快照。

    连同全部回合记录一起返回：跑团一局也就几十轮，一次给全比让前端自己
    拼接历史要简单可靠。
    """
    state = game.state
    return {
        "id": state.id,
        "scenario": state.scenario,
        "turn_count": state.turn_count,
        "over": state.over,
        "summary": state.summary,
        "character": state.character.to_dict(),
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
    """开局表单需要的选项。"""
    return {
        "backgrounds": [
            {"name": name, "attributes": attributes}
            for name, attributes in BACKGROUNDS.items()
        ],
        "scenarios": list(SCENARIOS),
    }


@router.post("/game/new")
def new_game(payload: NewGameRequest, request: Request) -> dict:
    """开一局新的，并让 GM 生成开场。"""
    store: GameStore = request.app.state.store
    game = store.create(payload.name, payload.background, payload.scenario)

    try:
        opening = game.engine.opening()
    except OllamaError as exc:
        store.drop(game.id)  # 开场都生成不了，这一局留着也没用
        raise HTTPException(status_code=502, detail=f"GM 没能开场：{exc}") from exc

    return {"ok": True, "game": _snapshot(game), "opening": opening}


@router.post("/game/turn")
def play_turn(payload: TurnRequest, request: Request) -> dict:
    """推进一个回合。"""
    store: GameStore = request.app.state.store
    game = _require_game(request, payload.game_id)

    try:
        result = store.play(game, payload.action)
    except GameError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except OllamaError as exc:
        raise HTTPException(status_code=502, detail=f"GM 没有回应：{exc}") from exc

    return {
        "ok": True,
        "narration": result.narration,
        "check": result.check,
        "changes": result.changes,
        "game": _snapshot(game),
    }


@router.post("/game/save")
def save_game(payload: GameRef, request: Request) -> dict:
    """把当前进度写进存档目录。"""
    game = _require_game(request, payload.game_id)
    path = game.state.save()
    return {"ok": True, "file": path.name, "turn_count": game.state.turn_count}


@router.get("/saves")
def list_saves() -> dict:
    """列出已有存档。"""
    from aigm.gamestate import GameState

    return {"ok": True, "saves": GameState.list_saves()}
