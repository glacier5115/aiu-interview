"""角色卡。

属性、生命值、物品、线索。**所有数值都由程序维护**——模型的职责是叙事，
不该让它凭空决定玩家还剩多少血、背包里多出什么东西。它只能提出「这里该掉
3 点血」，具体扣多少、能不能扣，由这里说了算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rules import ATTRIBUTES, hp_max_of, modifier_of

# 四个出身，属性总和都是 10，选哪个都能玩
BACKGROUNDS: dict[str, dict[str, int]] = {
    "战士": {"体魄": 4, "敏捷": 2, "心智": 2, "感知": 2},
    "游荡者": {"体魄": 2, "敏捷": 4, "心智": 3, "感知": 2},
    "学者": {"体魄": 2, "敏捷": 2, "心智": 4, "感知": 3},
    "行者": {"体魄": 3, "敏捷": 3, "心智": 2, "感知": 3},
}

DEFAULT_BACKGROUND = "行者"

STARTER_ITEMS = ("火把", "干粮")


@dataclass
class Character:
    """玩家扮演的角色。"""

    name: str
    background: str
    attributes: dict[str, int]
    hp: int
    hp_max: int
    inventory: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @classmethod
    def create(cls, name: str, background: str) -> "Character":
        """按出身建一个角色。"""
        picked = background if background in BACKGROUNDS else DEFAULT_BACKGROUND
        attributes = dict(BACKGROUNDS[picked])
        hp_max = hp_max_of(attributes["体魄"])
        return cls(
            name=(name or "无名者").strip()[:20],
            background=picked,
            attributes=attributes,
            hp=hp_max,
            hp_max=hp_max,
            inventory=list(STARTER_ITEMS),
        )

    @property
    def alive(self) -> bool:
        return self.hp > 0

    def modifier(self, attribute: str) -> int:
        """某项属性的调整值。"""
        return modifier_of(self.attributes.get(attribute, 2))

    def take_damage(self, amount: int) -> int:
        """扣血，返回实际扣掉的数值（不会扣成负数）。"""
        amount = max(0, int(amount))
        real = min(amount, self.hp)
        self.hp -= real
        return real

    def heal(self, amount: int) -> int:
        """回血，返回实际回复的数值（不会超过上限）。"""
        amount = max(0, int(amount))
        real = min(amount, self.hp_max - self.hp)
        self.hp += real
        return real

    def add_item(self, item: str) -> bool:
        item = (item or "").strip()[:30]
        if not item or item in self.inventory:
            return False
        self.inventory.append(item)
        return True

    def remove_item(self, item: str) -> bool:
        item = (item or "").strip()
        if item in self.inventory:
            self.inventory.remove(item)
            return True
        return False

    def add_note(self, text: str) -> bool:
        """记一条线索。重复的不再记。"""
        text = (text or "").strip()[:120]
        if not text or text in self.notes:
            return False
        self.notes.append(text)
        return True

    def to_dict(self) -> dict[str, Any]:
        """给前端用的结构。"""
        return {
            "name": self.name,
            "background": self.background,
            "attributes": [
                {
                    "name": key,
                    "value": self.attributes[key],
                    "modifier": modifier_of(self.attributes[key]),
                }
                for key in ATTRIBUTES
            ],
            "hp": self.hp,
            "hp_max": self.hp_max,
            "alive": self.alive,
            "inventory": list(self.inventory),
            "notes": list(self.notes),
        }

    def describe_for_gm(self) -> str:
        """给模型看的紧凑状态描述。"""
        attrs = "，".join(f"{name} {value}" for name, value in self.attributes.items())
        items = "、".join(self.inventory) or "无"
        return (
            f"{self.name}（{self.background}）｜生命 {self.hp}/{self.hp_max}"
            f"｜{attrs}｜携带：{items}"
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Character":
        return cls(
            name=data["name"],
            background=data["background"],
            attributes=dict(data["attributes"]),
            hp=int(data["hp"]),
            hp_max=int(data["hp_max"]),
            inventory=list(data.get("inventory", [])),
            notes=list(data.get("notes", [])),
        )
