"""世界观。

一份世界观包含：名字、一句话钩子、基调、设定正文。它决定 GM 描述世界时的
底色——同一个「推门」的动作，在悬疑世界里和轻快世界里写出来完全是两回事。

预置的几个直接写在代码里；玩家自己写或让 AI 生成的随存档一起保存，不单独落盘。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

# 这些基调只是给模型的取值词表，程序不按它做逻辑分支
TONES = ("悬疑", "苍凉", "黑暗", "轻快", "荒诞")


@dataclass
class World:
    """一份世界观。"""

    name: str = ""
    pitch: str = ""
    tone: str = ""
    details: str = ""
    origin: str = "preset"  # preset / user / generated

    @property
    def empty(self) -> bool:
        return not self.name and not self.details

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "pitch": self.pitch,
            "tone": self.tone,
            "details": self.details,
            "origin": self.origin,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "World":
        data = data or {}
        return cls(
            name=str(data.get("name") or ""),
            pitch=str(data.get("pitch") or ""),
            tone=str(data.get("tone") or ""),
            details=str(data.get("details") or ""),
            origin=str(data.get("origin") or "preset"),
        )

    def describe_for_gm(self) -> str:
        """拼成给模型看的一段。"""
        lines = [f"世界：{self.name}"]
        if self.tone:
            lines.append(f"基调：{self.tone}")
        if self.pitch:
            lines.append(f"钩子：{self.pitch}")
        if self.details:
            lines.append(f"设定：{self.details}")
        return "\n".join(lines)


# 每个预置世界都给了一个有张力的冲突，而不是一份风景介绍——
# 冒险得有个起点，而不是让 GM 和玩家一起站在原地找事做。
PRESETS: tuple[World, ...] = (
    World(
        name="雾中的旧磨坊",
        pitch="磨盘停了十年，可每到雾起，人们仍能听见它转动。",
        tone="悬疑",
        details=(
            "村子西边的老磨坊停了十年，磨盘早已锈死，但每到雾起的夜里，"
            "人们仍能听见它转动的声音。十年前磨坊主一家四口在一个雨夜消失，"
            "此后再没人敢靠近。近来村里的孩子又开始做同一个梦：雾里有声音在喊他们的名字。"
            "镇公所贴出了悬赏，去过的三批人里只回来过一个——是个哑巴。"
        ),
    ),
    World(
        name="沉没的灯塔",
        pitch="灯塔已经沉了一半，看守人还在每天点灯。",
        tone="苍凉",
        details=(
            "海角上的灯塔在半年前那场风暴里沉了一半，塔身斜插进礁石，"
            "露出水面的部分像一截断指。看守人没有离开，他住在塔顶，照旧每天点灯，"
            "尽管已经没有船会经过这条航线。有人说他在等一艘永远不会来的船；"
            "也有人说，那场风暴里有七个人失踪，而他记得每一个名字。"
        ),
    ),
    World(
        name="荒废的驿站",
        pitch="驿站的招牌早就不挂了，门却总是开着。",
        tone="黑暗",
        details=(
            "横穿荒原的古道早已废弃，但半途那座驿站仍在营业——招牌不挂，门却总开着。"
            "掌柜从不问来客的姓名，只收一样东西：一段你自己都不记得的往事。"
            "有人用童年换了一晚安眠，有人用爱人换回一条命。"
            "驿站后院埋着很多没有名字的包袱，据说每一个里都装着一个被卖掉的人。"
        ),
    ),
)


def preset_by_name(name: str) -> World | None:
    """按名字找预置世界。"""
    for world in PRESETS:
        if world.name == name:
            return world
    return None


def to_world(value: object, fallback: World | None = None) -> World:
    """把各种形式的输入统一成 World。

    接受三种写法：World 对象、字典（自定义或 AI 生成的内容）、预置世界的名字。
    认不出来就返回 fallback（默认是第一个预置世界）。

    收口在这里是有原因的：调用方可能从 HTTP 请求、存档文件或测试脚本进来，
    各自带着不同的形态。与其在每个入口都写一遍判断，不如只留这一个地方。
    """
    if isinstance(value, World):
        return value

    if isinstance(value, dict):
        world = World.from_dict(value)
        if not world.empty:
            return world

    if isinstance(value, str) and value.strip():
        found = preset_by_name(value.strip())
        return found or World(name=value.strip()[:16], origin="user")

    return fallback or PRESETS[0]
