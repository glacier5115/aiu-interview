"""骰子与检定规则。

纯逻辑：不依赖模型、不依赖网络，可以直接单测（`tests` 之类的东西不用搭框架，
import 进来调就行）。

规则是**刻意压简单**的。跑团的乐趣在叙事和选择，而本地跑的是 8B 模型——规则
越复杂，它越容易记错、算错、或者干脆编一个结果。所以这里只保留四属性 + d20
检定这一层骨架，复杂度留给 GM 的叙事能力。
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

# 四项属性，取值 1-5，2 是常人水平
ATTRIBUTES = ("体魄", "敏捷", "心智", "感知")

ATTRIBUTE_MIN = 1
ATTRIBUTE_MAX = 5
ATTRIBUTE_AVERAGE = 2

# 难度只有四档。给模型一个固定词表，它就不容易随口编一个 DC 出来。
DIFFICULTIES: dict[str, int] = {
    "容易": 8,
    "普通": 12,
    "困难": 16,
    "极难": 20,
}

DIE_SIDES = 20


@dataclass(frozen=True)
class CheckResult:
    """一次检定的完整结果。"""

    attribute: str
    value: int
    difficulty_label: str
    difficulty: int
    die: int
    modifier: int
    total: int
    success: bool
    critical: str  # "" / "大成功" / "大失败"

    def describe(self) -> str:
        """一句话把过程说清楚，便于展示在骰子日志里。"""
        head = f"{self.attribute}检定：d20={self.die}"
        if self.modifier:
            head += f" {'+' if self.modifier > 0 else '-'} {abs(self.modifier)}"
        head += f" = {self.total}，难度 {self.difficulty}（{self.difficulty_label}）"
        tail = self.critical or ("成功" if self.success else "失败")
        return f"{head} → {tail}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "attribute": self.attribute,
            "value": self.value,
            "difficulty_label": self.difficulty_label,
            "difficulty": self.difficulty,
            "die": self.die,
            "modifier": self.modifier,
            "total": self.total,
            "success": self.success,
            "critical": self.critical,
            "description": self.describe(),
        }


def modifier_of(value: int) -> int:
    """属性调整值：属性值减 2，范围 -1 ~ +3。"""
    return value - ATTRIBUTE_AVERAGE


def hp_max_of(might: int) -> int:
    """生命值上限：体魄越高越扛揍。"""
    return 10 + might * 2


def normalize_difficulty(label: str) -> tuple[str, int]:
    """把模型给的难度词规范成固定档位。

    模型偶尔会写「中等」「有点难」这类词，落不到规则表里。这里统一收口，
    认不出来就按「普通」处理，避免整局因为一个词卡住。
    """
    text = (label or "").strip()
    if text in DIFFICULTIES:
        return text, DIFFICULTIES[text]
    return "普通", DIFFICULTIES["普通"]


def resolve_check(
    attribute: str,
    value: int,
    difficulty_label: str,
    *,
    rng: random.Random | None = None,
) -> CheckResult:
    """掷一次 d20 检定。

    d20 掷出 20 记为大成功，掷出 1 记为大失败——不管加值多少，
    这条规则让冒险始终保留一点戏剧性。
    """
    if attribute not in ATTRIBUTES:
        attribute = ATTRIBUTES[0]

    label, difficulty = normalize_difficulty(difficulty_label)
    roll = (rng or random).randint(1, DIE_SIDES)
    modifier = modifier_of(value)
    total = roll + modifier

    if roll == DIE_SIDES:
        success, critical = True, "大成功"
    elif roll == 1:
        success, critical = False, "大失败"
    else:
        success, critical = total >= difficulty, ""

    return CheckResult(
        attribute=attribute,
        value=value,
        difficulty_label=label,
        difficulty=difficulty,
        die=roll,
        modifier=modifier,
        total=total,
        success=success,
        critical=critical,
    )


def clamp_attribute(value: int) -> int:
    """把属性值限制在合法范围内。"""
    return max(ATTRIBUTE_MIN, min(ATTRIBUTE_MAX, int(value)))
