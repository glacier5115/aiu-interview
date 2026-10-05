"""一整局的游戏状态。

角色、剧情摘要、回合记录。整体可以序列化成 JSON 存档，所以关掉页面再回来
还能接着玩。

「摘要 + 近期原文」这个组合是必须的：跑团是长对话，8B 模型的上下文放不下
一整场冒险，所以早期内容压缩成摘要，只有最近几轮保留原文。
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .character import Character
from .config import SAVES_DIR


@dataclass
class Turn:
    """一个回合里发生的事。"""

    index: int
    player: str
    narration: str
    check: dict[str, Any] | None = None
    changes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Turn":
        return cls(
            index=int(data["index"]),
            player=data["player"],
            narration=data["narration"],
            check=data.get("check"),
            changes=list(data.get("changes", [])),
        )


@dataclass
class GameState:
    """一局游戏的全量状态。"""

    id: str
    scenario: str
    character: Character
    opening: str = ""  # 开场叙事，存档时一并保存
    summary: str = ""
    # 摘要已经覆盖到第几轮（不含这一轮）。只有它之后、最近若干轮之前的内容
    # 才需要重新摘要，避免每轮都把全部历史重写一遍。
    summary_upto: int = 0
    turns: list[Turn] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def new(
        cls,
        name: str,
        background: str,
        scenario: str,
        attributes: dict[str, int] | None = None,
    ) -> "GameState":
        """开一局新的。attributes 传了就自定义属性，否则用身份的推荐值。"""
        return cls(
            id=uuid.uuid4().hex[:12],
            scenario=scenario.strip() or "无名之境",
            character=Character.create(name, background, attributes),
        )

    @property
    def turn_count(self) -> int:
        return len(self.turns)

    @property
    def over(self) -> bool:
        """角色倒下即结束。"""
        return not self.character.alive

    def recent_turns(self, count: int) -> list[Turn]:
        """最近 count 轮，用于构造提示词。"""
        return self.turns[-count:] if count > 0 else []

    def add_turn(self, turn: Turn) -> None:
        self.turns.append(turn)
        self.touched()

    def touched(self) -> None:
        self.updated_at = time.time()

    # ---------- 存档 ----------
    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "scenario": self.scenario,
            # 用 asdict 而不是手写字段列表：这样以后给 Character 加字段时，
            # 序列化不会悄悄漏掉它。手写的那版已经在本轮加 statuses/relations
            # 时丢过一次数据了。
            "character": asdict(self.character),
            "opening": self.opening,
            "summary": self.summary,
            "summary_upto": self.summary_upto,
            "turns": [turn.to_dict() for turn in self.turns],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GameState":
        return cls(
            id=data["id"],
            scenario=data["scenario"],
            character=Character.from_dict(data["character"]),
            opening=data.get("opening", ""),
            summary=data.get("summary", ""),
            summary_upto=int(data.get("summary_upto", 0)),
            turns=[Turn.from_dict(item) for item in data.get("turns", [])],
            created_at=float(data.get("created_at", time.time())),
            updated_at=float(data.get("updated_at", time.time())),
        )

    def save(self, directory: Path | None = None) -> Path:
        """写存档，返回文件路径。文件名带角色名，方便一眼认出是哪一局。"""
        target_dir = Path(directory or SAVES_DIR)
        target_dir.mkdir(parents=True, exist_ok=True)
        safe_name = "".join(ch for ch in self.character.name if ch.isalnum() or ch in "-_") or "hero"
        path = target_dir / f"{self.id}-{safe_name}.json"
        path.write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    @classmethod
    def load(cls, path: Path) -> "GameState":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls.from_dict(data)

    @staticmethod
    def list_saves(directory: Path | None = None) -> list[dict[str, Any]]:
        """列出所有存档的摘要信息，供界面选择。"""
        target_dir = Path(directory or SAVES_DIR)
        if not target_dir.exists():
            return []

        saves: list[dict[str, Any]] = []
        for path in sorted(target_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # 坏档跳过，不要让一个文件毁了整个列表
            saves.append(
                {
                    "file": path.name,
                    "id": data.get("id", ""),
                    "scenario": data.get("scenario", ""),
                    "hero": data.get("character", {}).get("name", ""),
                    "turns": len(data.get("turns", [])),
                    "updated_at": data.get("updated_at", 0),
                }
            )
        return saves
