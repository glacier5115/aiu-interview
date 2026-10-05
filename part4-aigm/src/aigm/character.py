"""角色卡。

属性、生命值、物品、线索、状态效果、人际关系。**所有数值都由程序维护**——
模型的职责是叙事，不该让它凭空决定玩家还剩多少血、背包里多出什么东西、
身上挂着什么状态。它只能提出「这里该掉 3 点血」「他该对你戒备」，能不能生效
由这里说了算。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .rules import ATTRIBUTES, hp_max_of, modifier_of, normalize_attributes

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
class Status:
    """一个持续中的状态效果，例如「扭伤」「被祝福」。"""

    name: str
    turns: int = 0  # 剩余回合数；0 表示需要剧情解除才会消失

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "turns": self.turns}


@dataclass
class Relation:
    """与一个 NPC 的关系。"""

    target: str
    attitude: str = "中立"

    def to_dict(self) -> dict[str, Any]:
        return {"target": self.target, "attitude": self.attitude}


@dataclass
class Persona:
    """角色的「人」的那一面：外貌、性格、动机、来历，以及一路长出来的特质。

    traits 是唯一会在游戏过程中变多的部分——其余几项开局定下后基本不动。
    """

    appearance: str = ""
    personality: str = ""
    motivation: str = ""
    background: str = ""
    traits: list[str] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return not any(
            (self.appearance, self.personality, self.motivation, self.background, self.traits)
        )

    def add_trait(self, text: str) -> bool:
        """记下一条特质。重复的不再记。"""
        text = (text or "").strip()[:60]
        if not text or text in self.traits:
            return False
        self.traits.append(text)
        return True

    def to_dict(self) -> dict[str, Any]:
        return {
            "appearance": self.appearance,
            "personality": self.personality,
            "motivation": self.motivation,
            "background": self.background,
            "traits": list(self.traits),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "Persona":
        data = data or {}
        return cls(
            appearance=data.get("appearance", ""),
            personality=data.get("personality", ""),
            motivation=data.get("motivation", ""),
            background=data.get("background", ""),
            traits=list(data.get("traits", [])),
        )


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
    title: str = ""
    persona: Persona = field(default_factory=Persona)
    statuses: list[Status] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)

    @classmethod
    def create(
        cls,
        name: str,
        background: str,
        attributes: dict[str, int] | None = None,
    ) -> "Character":
        """建一个角色。

        给了 attributes 就用它（先按规则修正），否则套用该身份推荐的那套。
        自定义身份时 background 是玩家自己填的名字，属性完全由 attributes 决定。
        """
        picked = (background or DEFAULT_BACKGROUND).strip()[:16] or DEFAULT_BACKGROUND
        if attributes:
            final_attributes = normalize_attributes(attributes)
        else:
            template = BACKGROUNDS.get(picked, BACKGROUNDS[DEFAULT_BACKGROUND])
            final_attributes = dict(template)

        hp_max = hp_max_of(final_attributes["体魄"])
        return cls(
            name=(name or "无名者").strip()[:20],
            background=picked,
            attributes=final_attributes,
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

    # ---------- 生命 ----------
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

    # ---------- 物品与线索 ----------
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

    # ---------- 状态效果 ----------
    def add_status(self, name: str, turns: int = 0) -> bool:
        """挂上一个状态。同名的会刷新持续回合，而不是叠成两条。"""
        name = (name or "").strip()[:20]
        if not name:
            return False
        turns = max(0, int(turns))
        for status in self.statuses:
            if status.name == name:
                status.turns = max(status.turns, turns)
                return True
        self.statuses.append(Status(name=name, turns=turns))
        return True

    def tick_statuses(self) -> list[str]:
        """回合结束时推进状态，返回这一轮自然消退的状态名。

        持续回合由程序数——模型只负责「挂上」这个动作。
        """
        expired: list[str] = []
        kept: list[Status] = []
        for status in self.statuses:
            if status.turns > 0:
                status.turns -= 1
                if status.turns == 0:
                    expired.append(status.name)
                    continue
            kept.append(status)
        self.statuses = kept
        return expired

    # ---------- 人际关系 ----------
    def set_relation(self, target: str, attitude: str) -> bool:
        """记录或更新与某个 NPC 的关系。态度没变就不动。"""
        target = (target or "").strip()[:20]
        if not target:
            return False
        attitude = (attitude or "中立").strip()[:20]
        for relation in self.relations:
            if relation.target == target:
                if relation.attitude == attitude:
                    return False
                relation.attitude = attitude
                return True
        self.relations.append(Relation(target=target, attitude=attitude))
        return True

    # ---------- 序列化 ----------
    def to_dict(self) -> dict[str, Any]:
        """给前端用的结构。"""
        return {
            "name": self.name,
            "title": self.title,
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
            "persona": self.persona.to_dict(),
            "statuses": [status.to_dict() for status in self.statuses],
            "relations": [relation.to_dict() for relation in self.relations],
            "inventory": list(self.inventory),
            "notes": list(self.notes),
        }

    def describe_for_gm(self) -> str:
        """给模型看的紧凑状态描述。"""
        attrs = "，".join(f"{name} {value}" for name, value in self.attributes.items())
        items = "、".join(self.inventory) or "无"

        head = f"{self.name}"
        if self.title:
            head += f"（{self.title}）"
        head += f"，{self.background}"

        line = f"{head}｜生命 {self.hp}/{self.hp_max}｜{attrs}｜携带：{items}"

        # 人设只带最要紧的两项，避免每轮都把整份设定塞进提示词
        if self.persona.motivation:
            line += f"｜目标：{self.persona.motivation}"
        if self.persona.traits:
            line += f"｜特质：{'、'.join(self.persona.traits)}"

        if self.statuses:
            marks = "、".join(
                f"{s.name}（剩 {s.turns} 回合）" if s.turns else s.name
                for s in self.statuses
            )
            line += f"｜状态：{marks}"
        if self.relations:
            pairs = "、".join(f"{r.target}对你{r.attitude}" for r in self.relations)
            line += f"｜关系：{pairs}"
        return line

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
            title=data.get("title", ""),
            persona=Persona.from_dict(data.get("persona")),
            statuses=[Status(**item) for item in data.get("statuses", [])],
            relations=[Relation(**item) for item in data.get("relations", [])],
        )
