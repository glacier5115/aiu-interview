"""GM 引擎：把玩家的行动推进成一个回合。

流程刻意分成两步，因为「叙事」和「裁决」必须分开：

    1. 模型描写行动、并判断要不要检定——此时它还不知道结果
    2. 程序掷骰，把结果喂回去，模型写出结局并提出状态变更

如果让它一次生成全过程，它会直接编一个成功或失败的结果，骰子就形同虚设了。
这条分工是「模型负责叙事、程序负责规则」的具体体现，也是整个作品能不能
当好一个 GM 的关键。
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Iterator

from shared.llm_chat.client import OllamaClient

from . import config, jsonstream, prompts
from .gamestate import GameState, Turn
from .rules import (
    ATTRIBUTES,
    ATTRIBUTE_POINTS,
    CheckResult,
    normalize_attributes,
    resolve_check,
)
from .worlds import World


class GameError(RuntimeError):
    """可以直接展示给玩家的错误。"""


@dataclass
class TurnResult:
    """一个回合的产出。"""

    narration: str
    check: dict | None
    changes: list[str]
    turn: Turn
    over: bool


class GameEngine:
    """驱动一局游戏。"""

    def __init__(
        self,
        client: OllamaClient,
        state: GameState,
        rng: random.Random | None = None,
    ) -> None:
        self.client = client
        self.state = state
        self.rng = rng or random.Random()

    # ---------------- 主流程 ----------------
    def play(self, action: str) -> TurnResult:
        """非流式地推进一个回合。

        实现上只是把 ``play_stream`` 的事件消费掉。刻意不另写一套逻辑——
        两条路径各写一遍的话，早晚会在某个分支上分叉。
        """
        for event in self.play_stream(action):
            if event["type"] == "done":
                return event["result"]
        raise GameError("回合没有正常结束")

    def play_stream(self, action: str) -> Iterator[dict]:
        """流式推进一个回合，逐个产出事件。

        事件类型：

        ``phase``    阶段提示（前端可以显示「GM 正在思考」／「已掷骰」）
        ``delta``    叙事增量。带 ``reset`` 时表示这一段要**替换**而不是追加
        ``check``    掷骰结果（已经由程序判定完毕）
        ``changes``  状态变化
        ``done``     回合结束，附带完整的 ``TurnResult``
        """
        if self.state.over:
            raise GameError("这一局已经结束了——角色已经倒下，开新的一局吧")

        action = (action or "").strip()
        if not action:
            raise GameError("先写下你的行动")

        yield {"type": "phase", "phase": "action"}

        # 第一步：描写行动 + 判断要不要检定（此时模型还不知道结果）
        decision, narration = yield from self._stream_step(
            self._action_messages(action), temperature=config.GM_TEMPERATURE
        )
        decision = decision or {}
        if not narration:
            narration = str(decision.get("narration") or "").strip()

        if not narration:
            raise GameError("GM 没有给出叙事，请再试一次")

        check_result: CheckResult | None = None
        changes: list[str] = []

        request = decision.get("check")
        if isinstance(request, dict):
            # 第二步：程序掷骰，再把结果喂回去让模型写结局
            check_result = self._roll(action, request)
            yield {"type": "check", "check": check_result.to_dict()}
            yield {"type": "phase", "phase": "outcome"}

            # 先推一个换行：第二段要另起一段。前端按空行分段落，后端存的也是
            # 两段拼接的结果——这个分隔符让两边显示保持一致。
            yield {"type": "delta", "text": "\n\n"}

            outcome, resolved = yield from self._stream_step(
                self._outcome_messages(action, check_result),
                temperature=config.STRUCTURED_TEMPERATURE,
            )
            if resolved:
                # 接在行动描写后面，作为同一段叙事的后续——而不是把它整个换掉。
                # 换掉的话，玩家刚逐字读完的文字会当着面消失，观感很差。
                narration = f"{narration}\n\n{resolved}"
            changes = self._apply_changes((outcome or {}).get("state_changes"))

        # 状态效果的持续回合每回合推进一次。这件事必须由程序数——
        # 让模型记账的话，几轮之后它就会忘记某个状态该不该还在。
        for expired in self.state.character.tick_statuses():
            changes.append(f"状态消退：{expired}")

        turn = Turn(
            index=self.state.turn_count + 1,
            player=action,
            narration=narration,
            check=check_result.to_dict() if check_result else None,
            changes=changes,
        )
        self.state.add_turn(turn)
        self._maybe_refresh_summary()

        if changes:
            yield {"type": "changes", "changes": changes}

        yield {
            "type": "done",
            "result": TurnResult(
                narration=narration,
                check=turn.check,
                changes=changes,
                turn=turn,
                over=self.state.over,
            ),
        }

    def _stream_step(
        self,
        messages: list[dict],
        *,
        temperature: float,
        reset: bool = False,
    ):
        """跑一次模型调用并流式产出 ``delta`` 事件，最后返回 (解析结果, 叙事文本)。

        解析失败会**降级**：只要流式收到的叙事是好的，就把它当纯文本用——
        玩家已经看着字一个个出来了，这时再报错重来最伤人。只有连叙事都没收到
        （比如模型吐了一堆不合规的东西），才退回非流式重试一次。
        """
        buffer = ""
        tracker = jsonstream.FieldDelta("narration")
        first = reset

        for chunk in self.client.chat_stream(
            messages, json_mode=True, temperature=temperature
        ):
            buffer += chunk
            piece = tracker.feed(buffer)
            if piece:
                yield {"type": "delta", "text": piece, "reset": first}
                first = False  # 只有第一片需要让前端清空

        narration = tracker.full.strip()

        try:
            data = json.loads(buffer)
            if isinstance(data, dict):
                return data, narration
        except ValueError:
            pass

        if narration:
            return {}, narration  # 降级：JSON 坏了，但叙事是好的

        data = self._ask_json(messages, temperature=temperature)
        narration = str(data.get("narration") or "").strip()
        if narration:
            yield {"type": "delta", "text": narration, "reset": first}
        return data, narration

    # ---------------- 与模型交互 ----------------
    def apply_persona(self, data: dict) -> None:
        """把一份人设写进角色卡。

        只覆盖有值的那几项——玩家自己写的内容不该被模型的空白抹掉。
        属性不在这里处理：建角色时它就已经定了。
        """
        character = self.state.character

        title = str(data.get("title") or "").strip()[:10]
        if title:
            character.title = title

        persona = character.persona
        for field, limit in (
            ("appearance", 80),
            ("personality", 80),
            ("motivation", 80),
            ("background", 300),
        ):
            value = str(data.get(field) or "").strip()
            if value:
                setattr(persona, field, value[:limit])

        trait = str(data.get("trait") or "").strip()
        if trait:
            persona.add_trait(trait)

    def opening(self) -> str:
        """生成开场叙事。开新局时调用一次。

        开场是一段普通文本而不是 JSON——它没有结构化信息，只是把玩家带进情境。
        """
        messages = [
            {"role": "system", "content": prompts.OPENING_SYSTEM},
            {"role": "user", "content": prompts.build_context(self.state, recent_limit=0)},
        ]
        return self.client.chat(messages, temperature=config.GM_TEMPERATURE).strip()

    def _action_messages(self, action: str) -> list[dict]:
        """第一步的消息：描写行动 + 决定是否检定。"""
        return [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": f"玩家行动：{action}"},
        ]

    def _outcome_messages(self, action: str, check: CheckResult) -> list[dict]:
        """第二步的消息：把掷骰结果告诉 GM，让它写结局。"""
        return [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": prompts.build_resolve_prompt(action, check.describe()),
            },
        ]

    def _ask_action(self, action: str) -> dict:
        """第一步（非流式）：让 GM 描写行动并决定是否检定。"""
        return self._ask_json(
            self._action_messages(action), temperature=config.GM_TEMPERATURE
        )

    def _ask_outcome(self, action: str, check: CheckResult) -> dict:
        """第二步（非流式）：把掷骰结果告诉 GM，让它写结局。"""
        return self._ask_json(
            self._outcome_messages(action, check),
            temperature=config.STRUCTURED_TEMPERATURE,
        )

    def _system_prompt(self) -> str:
        context = prompts.build_context(self.state, recent_limit=config.RECENT_TURNS)
        return f"{prompts.GM_SYSTEM}\n\n{context}"

    def _ask_json(self, messages: list[dict], *, temperature: float) -> dict:
        """调一次模型并解析成 JSON。

        json_mode 让 Ollama 强制输出合法 JSON；即便如此仍然要防一手——
        偶尔会拿到数组或半个对象，这里统一转成可读错误，别让整局崩掉。
        """
        raw = self.client.chat(messages, json_mode=True, temperature=temperature)
        try:
            data = json.loads(raw)
        except ValueError as exc:
            raise GameError(f"GM 返回的内容不是合法 JSON：{raw[:160]}") from exc
        if not isinstance(data, dict):
            raise GameError("GM 返回的 JSON 结构不对")
        return data

    # ---------------- 规则与状态 ----------------
    def _roll(self, action: str, request: dict) -> CheckResult:
        """按模型提出的检定掷骰。

        属性名和难度都由程序收口：模型写了个不存在的属性或难度词，也不会
        把规则带跑偏。
        """
        attribute = str(request.get("attribute") or "").strip()
        if attribute not in ATTRIBUTES:
            attribute = ATTRIBUTES[0]

        value = self.state.character.attributes.get(attribute, 2)
        difficulty = str(request.get("difficulty") or "普通")
        return resolve_check(attribute, value, difficulty, rng=self.rng)

    def _apply_changes(self, raw_changes: object) -> list[str]:
        """把模型提出的状态变更落到角色卡上。

        模型只是**提议**，能不能生效由这里判断：伤害会夹取、回血不会超上限、
        物品不会重复。即使模型算错或者乱给，游戏状态也不会失控——这是把
        「规则」和「叙事」分开之后拿到的第二层保险。
        """
        if not isinstance(raw_changes, list):
            return []

        applied: list[str] = []
        for item in raw_changes:
            if not isinstance(item, dict):
                continue

            kind = item.get("type")
            if kind == "damage":
                real = self.state.character.take_damage(item.get("value", 0))
                if real:
                    reason = item.get("reason") or "受伤"
                    applied.append(f"失去 {real} 点生命（{reason}）")
            elif kind == "heal":
                real = self.state.character.heal(item.get("value", 0))
                if real:
                    applied.append(f"恢复 {real} 点生命")
            elif kind == "item_add":
                name = str(item.get("item") or "")
                if self.state.character.add_item(name):
                    applied.append(f"获得物品：{name}")
            elif kind == "item_remove":
                name = str(item.get("item") or "")
                if self.state.character.remove_item(name):
                    applied.append(f"失去物品：{name}")
            elif kind == "note":
                text = str(item.get("text") or "")
                if self.state.character.add_note(text):
                    applied.append(f"记下线索：{text}")
            elif kind == "status":
                name = str(item.get("name") or "")
                if self.state.character.add_status(name, item.get("turns", 0)):
                    applied.append(f"状态：{name}")
            elif kind == "relation":
                target = str(item.get("target") or "")
                attitude = str(item.get("attitude") or "中立")
                if self.state.character.set_relation(target, attitude):
                    applied.append(f"关系变化：{target}对你{attitude}")
            elif kind == "trait":
                text = str(item.get("text") or "")
                if self.state.character.persona.add_trait(text):
                    applied.append(f"新特质：{text}")

        return applied

    # ---------------- 剧情摘要 ----------------
    def _maybe_refresh_summary(self) -> None:
        """把早期回合压进摘要。

        不做这件事的话，跑团进行到几十轮时上下文就装不下了。摘要只覆盖
        「最近 N 轮之前」的内容，逐段向前推进，不重复处理。
        """
        tail_start = max(0, self.state.turn_count - config.RECENT_TURNS)
        pending = self.state.turns[self.state.summary_upto : tail_start]
        if len(pending) < config.SUMMARY_EVERY:
            return

        messages = [
            {"role": "system", "content": prompts.SUMMARY_SYSTEM},
            {
                "role": "user",
                "content": prompts.build_summary_prompt(self.state.summary, pending),
            },
        ]

        try:
            summary = self.client.chat(
                messages, temperature=config.STRUCTURED_TEMPERATURE
            ).strip()
        except Exception:  # noqa: BLE001  摘要失败不该打断游戏
            return

        if summary:
            self.state.summary = summary
            self.state.summary_upto = tail_start
            self.state.touched()


def complete_persona(
    client: OllamaClient,
    name: str,
    background: str,
    fields: dict[str, str] | None = None,
    attributes: dict[str, int] | None = None,
) -> dict:
    """让模型补全并润色人设，返回完整字段（含属性建议）。

    刻意做成**不碰任何状态**的纯函数：开局界面要能反复「重新生成」直到满意，
    所以这一步不能有副作用。写进角色卡是 ``apply_persona`` 的事。
    """
    messages = [
        {"role": "system", "content": prompts.PERSONA_SYSTEM},
        {
            "role": "user",
            "content": prompts.build_persona_prompt(name, background, fields, attributes),
        },
    ]
    raw = client.chat(messages, json_mode=True, temperature=config.GM_TEMPERATURE)

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise GameError(f"人设生成失败，模型返回的不是 JSON：{raw[:120]}") from exc
    if not isinstance(data, dict):
        raise GameError("人设生成失败，模型返回的结构不对")

    return {
        "title": str(data.get("title") or "").strip()[:10],
        "appearance": str(data.get("appearance") or "").strip()[:80],
        "personality": str(data.get("personality") or "").strip()[:80],
        "motivation": str(data.get("motivation") or "").strip()[:80],
        "background": str(data.get("background") or "").strip()[:300],
        "trait": str(data.get("trait") or "").strip()[:60],
        # 模型给的分配不一定合法，统一过一遍规则再交出去
        "attributes": normalize_attributes(data.get("attributes"), ATTRIBUTE_POINTS),
    }


def complete_world(
    client: OllamaClient,
    keywords: str = "",
    name: str = "",
    tone: str = "",
) -> World:
    """让模型生成一份世界观。只生成，不碰任何状态——和 complete_persona 一样，
    这样开局界面才能反复「重新生成」。"""
    messages = [
        {"role": "system", "content": prompts.WORLD_SYSTEM},
        {"role": "user", "content": prompts.build_world_prompt(keywords, name, tone)},
    ]
    raw = client.chat(messages, json_mode=True, temperature=config.GM_TEMPERATURE)

    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise GameError(f"世界观生成失败，模型返回的不是 JSON：{raw[:120]}") from exc
    if not isinstance(data, dict):
        raise GameError("世界观生成失败，模型返回的结构不对")

    return World(
        name=str(data.get("name") or name or "无名之境").strip()[:16],
        pitch=str(data.get("pitch") or "").strip()[:80],
        tone=str(data.get("tone") or tone or "").strip()[:8],
        details=str(data.get("details") or "").strip()[:600],
        origin="generated",
    )
