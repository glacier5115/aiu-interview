"""进行中的对局。

服务端在内存里维护若干局游戏，前端拿着 game_id 来回操作。关掉服务对局就没了，
要长期保留得显式存档（见 gamestate 的 save/load）。

两条并发约定：字典读写用锁保护；**整局对话串行化**——本地模型一次只能处理
一个请求，并发推进同一局会让上下文错乱。
"""

from __future__ import annotations

import random
import threading
from copy import deepcopy
from dataclasses import dataclass

from shared.llm_chat.client import OllamaClient

from aigm.gamestate import GameState
from aigm.gm import GameEngine
from aigm.worlds import World


@dataclass
class Game:
    """一局进行中的游戏：状态 + 引擎。"""

    state: GameState
    engine: GameEngine

    @property
    def id(self) -> str:
        return self.state.id


class GameStore:
    """对局的容器。"""

    def __init__(self, client: OllamaClient, rng: random.Random | None = None) -> None:
        self._client = client
        # 允许注入随机源，测试时可以固定骰子结果
        self._rng = rng
        self._games: dict[str, Game] = {}
        self._guard = threading.Lock()
        self._turn_lock = threading.Lock()

    def create(
        self,
        name: str,
        background: str,
        world: World | dict | str | None = None,
        attributes: dict[str, int] | None = None,
    ) -> Game:
        """开一局新的。"""
        state = GameState.new(name, background, world, attributes)
        engine = GameEngine(self._client, state, rng=self._rng)
        game = Game(state=state, engine=engine)
        with self._guard:
            self._games[game.id] = game
        return game

    def adopt(self, state: GameState) -> Game:
        """把一份存档载入内存，接着玩。"""
        engine = GameEngine(self._client, state, rng=self._rng)
        game = Game(state=state, engine=engine)
        with self._guard:
            self._games[game.id] = game
        return game

    def get(self, game_id: str) -> Game | None:
        with self._guard:
            return self._games.get(game_id)

    def require(self, game_id: str) -> Game:
        game = self.get(game_id)
        if game is None:
            raise KeyError(game_id)
        return game

    def drop(self, game_id: str) -> bool:
        with self._guard:
            return self._games.pop(game_id, None) is not None

    def play_stream(self, game: Game, action: str):
        """流式推进一个回合。整局串行，并且**中断安全**。

        前端可能在生成中途断开（用户点了「停止」）。那时这一轮的伤害、物品
        已经写进角色卡了，但回合还没提交——用一份快照把它退回去，免得留下
        「掉了血却没有这一回合」的脏状态。

        角色卡很小，每次深拷贝一份的代价可以忽略。
        """
        snapshot = deepcopy(game.state.character)
        committed = False

        with self._turn_lock:
            try:
                for event in game.engine.play_stream(action):
                    if event["type"] == "done":
                        committed = True
                    yield event
            finally:
                if not committed:
                    game.state.character = snapshot

    def count(self) -> int:
        with self._guard:
            return len(self._games)
