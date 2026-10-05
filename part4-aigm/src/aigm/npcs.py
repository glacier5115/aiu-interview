"""NPC 图鉴。

跑团的核心是人物。没有这张表的话，GM 每一轮都在重新认识同一个铁匠——
名字会变、性格会变、说多了还会自相矛盾。所以这里做两件事：把 NPC 存下来，
以及在组装提示词时把「该 GM 知道的」带上。

有个细节值得单独说：**秘密字段对玩家是不可见的**。GM 得知道它才能演出
（比如让一个藏着事的人说话吞吞吐吐），但玩家看到就没悬念了。所以序列化
分两个方法——``for_gm`` 给模型，``to_dict`` 给前端。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class NPC:
    """一个有名有姓的人物。"""

    name: str
    identity: str = ""  # 身份：磨坊主、巡夜人……
    appearance: str = ""  # 外貌，一句话
    speech: str = ""  # 说话风格，一句话
    motive: str = ""  # 明面上的动机
    secret: str = ""  # 隐藏动机或秘密——只给 GM 看
    attitude: str = "中立"  # 对玩家的态度
    status: str = "active"  # active / gone

    def merge(self, data: dict[str, Any]) -> None:
        """用新信息更新这个 NPC。**只覆盖有值的字段**。

        模型每次提到同一个人时信息量可能不同：有时只给个态度，有时补一句外貌。
        空值直接跳过，免得后一次的空字符串把前面辛苦写好的设定抹掉。
        """
        for field in ("identity", "appearance", "speech", "motive", "secret"):
            value = str(data.get(field) or "").strip()
            if value:
                setattr(self, field, value[:120])

        attitude = str(data.get("attitude") or "").strip()
        if attitude:
            self.attitude = attitude[:16]

        status = str(data.get("status") or "").strip()
        if status in ("active", "gone"):
            self.status = status

        name = str(data.get("name") or "").strip()
        if name and not self.name:
            self.name = name[:20]

    def for_gm(self) -> str:
        """给模型看的完整描述（含秘密）。"""
        parts = [f"{self.name}（{self.identity or '身份不明'}）"]
        if self.appearance:
            parts.append(f"外貌：{self.appearance}")
        if self.speech:
            parts.append(f"说话风格：{self.speech}")
        if self.motive:
            parts.append(f"明面动机：{self.motive}")
        if self.secret:
            parts.append(f"隐藏动机：{self.secret}")
        parts.append(f"对玩家：{self.attitude}")
        return "；".join(parts)

    def to_dict(self) -> dict[str, Any]:
        """给前端看的——**不含秘密**。"""
        return {
            "name": self.name,
            "identity": self.identity,
            "appearance": self.appearance,
            "speech": self.speech,
            "motive": self.motive,
            "attitude": self.attitude,
            "status": self.status,
            "has_secret": bool(self.secret),  # 只提示「他有事瞒着」，不透露是什么
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "NPC":
        data = data or {}
        return cls(
            name=str(data.get("name") or ""),
            identity=str(data.get("identity") or ""),
            appearance=str(data.get("appearance") or ""),
            speech=str(data.get("speech") or ""),
            motive=str(data.get("motive") or ""),
            secret=str(data.get("secret") or ""),
            attitude=str(data.get("attitude") or "中立"),
            status=str(data.get("status") or "active"),
        )


def find(npcs: list[NPC], name: str) -> NPC | None:
    """按名字找人。名字做过去空白处理，避免同一个人的两次记录对不上。"""
    target = (name or "").strip()
    if not target:
        return None
    for npc in npcs:
        if npc.name == target:
            return npc
    return None


def upsert(npcs: list[NPC], data: dict[str, Any]) -> tuple[NPC, bool]:
    """记下一个人：有就更新，没有就新建。返回 (npc, 是否新建)。

    名字为空时返回 (占位对象, False) 并且不入库——模型偶尔会给出没名字的人物，
    与其存一条无名的记录，不如直接丢掉。
    """
    name = str(data.get("name") or "").strip()[:20]
    if not name:
        return NPC(name=""), False

    existing = find(npcs, name)
    if existing is not None:
        existing.merge(data)
        return existing, False

    npc = NPC(name=name)
    npc.merge(data)
    npcs.append(npc)
    return npc, True
