"""GM 的提示词。

跑团能不能玩起来，八成取决于这一层。核心约束有两条：

1. **叙事与裁决分离**。第一轮只让模型描写「行动的过程」，不准写出结果——
   因为结果取决于还没掷的骰子。它一旦提前写了「你成功翻过墙」，骰子就白掷了。
2. **输出必须是 JSON**。靠 Ollama 的 `format=json` 强制，再配上字段说明和示例，
   8B 模型也能稳定产出结构化指令。

占位符用 `__XXX__` 而不是 `str.format`，因为提示词里有大量 JSON 花括号，
用 format 得把每个括号都写成双份，改起来很容易出错。
"""

from __future__ import annotations

from .rules import ATTRIBUTES, DIFFICULTIES
from .worlds import TONES

_ATTRIBUTE_TEXT = "、".join(ATTRIBUTES)
_DIFFICULTY_TEXT = "、".join(f"{name} {value}" for name, value in DIFFICULTIES.items())


GM_SYSTEM = f"""你是一场桌面角色扮演游戏的主持人（GM）。你描述世界、扮演 NPC、推进剧情，并在恰当的时机要求玩家的角色做检定。

## 世界与规则
- 角色有四项属性：{_ATTRIBUTE_TEXT}。取值 1-5，2 是常人水平。
- 只有当行动结果不确定、且失败会有代价时，才要求检定。
- 检定用 d20：掷骰点数 + 属性调整值 ≥ 难度即成功。调整值 = 属性值 - 2。
- 难度只有四档：{_DIFFICULTY_TEXT}。
- 平常的、必然成功的行动直接叙述结果，不要要求检定。

## 你必须输出的 JSON
{{
  "narration": "对行动过程的描写",
  "check": null 或 {{"attribute": "属性名", "difficulty": "难度名", "reason": "为什么需要检定"}}
}}

## 铁律
- narration 里**绝对不能**写出行动的结果。「你纵身跃过围墙」是错的，「你退后几步，助跑冲向墙边」是对的——结果要等骰子掷完才知道。
- 如果不需要检定（check 为 null），narration 就是完整叙事，可以包含结果。
- **观察、打量、回忆、交谈这类没有风险的行动不需要检定**，直接叙述即可。只有可能受伤、可能失去什么、或者成败两可的行动才值得掷骰子。
- 一轮最多要求一次检定。
- attribute 只能从 {_ATTRIBUTE_TEXT} 里选，difficulty 只能从四档里选。
- 只输出 JSON，不要有任何其他内容。

## 示例
玩家：我想翻过那堵墙
{{"narration": "你后退几步，助跑冲向墙边，指尖扒住砖缝向上发力，碎石簌簌往下掉。", "check": {{"attribute": "敏捷", "difficulty": "普通", "reason": "徒手翻越围墙"}}}}

玩家：我看看房间里有什么
{{"narration": "房间不大。半人高的旧书堆在墙角，一只落灰的铜烛台立在窗边，窗帘被穿堂风吹得鼓起来。桌上摊着一张没画完的地图。", "check": null}}"""


GM_RESOLVE = """上一步的检定已经掷完，结果如下。请据此写这一回合的结局。

## 玩家的行动
__ACTION__

## 检定结果
__CHECK__

## 你必须输出的 JSON
{
  "narration": "结果如何发生、世界如何回应",
  "state_changes": []
}

state_changes 是数组，没有变化就填空数组。可用类型：
- {"type": "damage", "value": 3, "reason": "从墙上摔下来"}
- {"type": "heal", "value": 2, "reason": "短暂休息"}
- {"type": "item_add", "item": "锈迹斑斑的铁钥匙"}
- {"type": "item_remove", "item": "火把"}
- {"type": "note", "text": "得知磨坊主与失踪案有关"}
- {"type": "status", "name": "扭伤脚踝", "turns": 3}
  持续状态。turns 是还能持续几回合；填 0 表示要等剧情解除。只在确实受伤、着迷、被诅咒这类情况下使用。
- {"type": "relation", "target": "老磨坊主", "attitude": "戒备"}
  与某个 NPC 的关系变化。attitude 用一个短词描述，例如「友好」「戒备」「畏惧」「感激」。
- {"type": "trait", "text": "面对火时会本能地犹豫"}
  角色新暴露或新长出的特质。只在情节确实揭示、改变了角色性格时使用——一局出现两三次就够了，不要每轮都给。

## 铁律
- 只在情节确实需要时改变状态。失败不等于必然受伤，成功也不等于必有奖励。
- damage 的数值要与情节分量相称：擦伤 1-2，重击 3-5。
- 不要凭空给玩家发物品，除非剧情里真的得到了。
- 状态和关系变化要克制：一场小遭遇不该让玩家多出三个状态、认识两个新朋友。
- 只输出 JSON，不要有任何其他内容。"""


SUMMARY_SYSTEM = """你在为一场桌面角色扮演游戏维护「剧情摘要」。

把给定的旧摘要和新增回合合并成一段不超过 200 字的摘要，只保留：出场人物、地点、已经发生的关键事件、尚未解决的线索。

只写已经发生的事，不要写玩家可能做什么，不要评论，不要任何前后缀。直接输出摘要正文。"""


OPENING_SYSTEM = """你是一场桌面角色扮演游戏的主持人（GM）。请为这场冒险写一段开场。

## 要求
- 150 字以内，第二人称（「你」）。
- 交代清楚：你身处何地、正在面对什么、眼前最紧迫的问题是什么。
- 直接进入情境，不要寒暄，不要问玩家想做什么。
- 只输出叙事正文，不要 JSON，不要任何前后缀。"""


PERSONA_SYSTEM = """你是一个桌面角色扮演游戏的角色设计师。请为玩家生成一份角色人设。

## 你必须输出的 JSON
{
  "title": "绰号或头衔，两到四个字",
  "appearance": "外貌，一句话",
  "personality": "性格，一句话",
  "motivation": "他想要什么，一句话",
  "background": "来历，两三句话",
  "trait": "一个鲜明的特质",
  "attributes": {"体魄": 3, "敏捷": 2, "心智": 2, "感知": 3}
}

## 要求
- 中文，简洁有力，不要堆砌形容词。
- 要有具体细节，别写「勇敢善良」这种空话——「左手小指少了一截」比「经历过磨难」好得多。
- **玩家已经写好的部分要原样保留**。你的任务是补全空缺、把过于简略的地方写具体，而不是另起炉灶重写一遍。
- attributes 必须和人设对得上：一个老兵不该敏捷 5 而体魄 1，成天泡在书里的人也不该体魄 4。四项总和必须正好等于 10，每项在 1-5 之间。
- trait 要能影响实际行为，例如「对火焰有本能的恐惧」，而不是「他很勇敢」这类评价。
- 只输出 JSON，不要有任何其他内容。"""


_PERSONA_FIELDS = (    ("appearance", "外貌"),
    ("personality", "性格"),
    ("motivation", "目标"),
    ("background", "来历"),
    ("trait", "特质"),
)


def build_persona_prompt(    name: str,
    background: str,
    fields: dict[str, str] | None = None,
    attributes: dict[str, int] | None = None,
) -> str:
    """拼出给角色设计师的输入。

    玩家填了的部分原样带进去，并明确区分「已给定」与「待补全」——分得越清楚，
    模型越不会去动玩家已经写好的东西。
    """
    fields = fields or {}
    lines = [f"角色名：{name}", f"身份：{background}"]

    if attributes:
        summary = "，".join(f"{key} {value}" for key, value in attributes.items())
        lines.append(f"属性（玩家已分配，不要改）：{summary}")

    pairs = [(label, fields.get(key, "").strip()) for key, label in _PERSONA_FIELDS]
    filled = [(label, value) for label, value in pairs if value]
    empty = [label for label, value in pairs if not value]

    if filled:
        lines.append("\n玩家已经写好的（原样保留，不要改写）：")
        lines.extend(f"- {label}：{value}" for label, value in filled)

    if empty:
        lines.append("\n需要你补全的：" + "、".join(empty))
    elif not filled:
        lines.append("\n玩家什么都没填，请自由发挥，但气质要和身份相称。")

    return "\n".join(lines)


WORLD_SYSTEM = f"""你是一个桌面角色扮演游戏的世界观设计师。

## 你必须输出的 JSON
{{
  "name": "世界名，两到六个字",
  "pitch": "一句话钩子，让人想进去看看",
  "tone": "基调，从这些里选一个：{'、'.join(TONES)}",
  "details": "设定正文，200 到 300 字"
}}

## details 里要写清楚
- 这是什么地方、什么时代。
- 有什么势力、什么规矩、什么禁忌。
- **至少埋一个有张力的冲突或谜团**，作为冒险的起点。

## 要求
- 中文，具体、有画面感，不要写成说明书。
- 别堆砌形容词——一个准确的细节比十句形容词管用（「露出水面的塔身像一截断指」胜过长篇描写）。
- 如果玩家给了关键词，把它们揉进去，但不要生硬地罗列。
- 只输出 JSON，不要有任何其他内容。"""


def build_world_prompt(keywords: str = "", name: str = "", tone: str = "") -> str:
    """拼出给世界观设计师的输入。"""
    lines = []
    if name.strip():
        lines.append(f"世界名（玩家给定）：{name.strip()}")
    if tone.strip():
        lines.append(f"基调（玩家给定）：{tone.strip()}")
    if keywords.strip():
        lines.append(f"玩家的关键词：{keywords.strip()}")
    if not lines:
        lines.append("玩家没有给任何提示，请自由发挥，但必须有一个明确的冲突或谜团。")
    return "\n".join(lines)


def build_context(state, *, recent_limit: int) -> str:
    """把角色状态与近期剧情拼成一段背景，放在 system 消息里。"""
    lines = [
        "## 世界",
        state.world.describe_for_gm(),
        "",
        "## 当前状态",
        state.character.describe_for_gm(),
    ]

    if state.summary:
        lines.append(f"\n## 前情提要\n{state.summary}")

    recent = state.recent_turns(recent_limit)
    if recent:
        lines.append("\n## 最近的经历")
        for turn in recent:
            lines.append(f"玩家：{turn.player}")
            lines.append(f"GM：{turn.narration}")
            if turn.check:
                lines.append(f"（检定：{turn.check.get('description', '')}）")

    return "\n".join(lines)


def build_resolve_prompt(action: str, check_text: str) -> str:
    """第二步的提示：把行动与掷骰结果一起交给模型。"""
    return GM_RESOLVE.replace("__ACTION__", action).replace("__CHECK__", check_text)


def build_summary_prompt(old_summary: str, turns: list) -> str:
    """把旧摘要和待合并的回合写成一段输入。"""
    blocks = []
    if old_summary:
        blocks.append(f"已有摘要：\n{old_summary}")
    blocks.append("新增的经历：")
    for turn in turns:
        blocks.append(f"- 玩家：{turn.player}")
        blocks.append(f"  GM：{turn.narration}")
    return "\n".join(blocks)
