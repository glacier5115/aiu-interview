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

from shared.llm_chat.client import OllamaClient

from . import config, prompts
from .gamestate import GameState, Turn
from .rules import ATTRIBUTES, CheckResult, resolve_check


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
        """推进一个回合。"""
        if self.state.over:
            raise GameError("这一局已经结束了——角色已经倒下，开新的一局吧")

        action = (action or "").strip()
        if not action:
            raise GameError("先写下你的行动")

        # 第一步：描写行动 + 判断要不要检定（此时模型不知道结果）
        decision = self._ask_action(action)
        narration = str(decision.get("narration") or "").strip()
        if not narration:
            raise GameError("GM 没有给出叙事，请再试一次")

        check_result: CheckResult | None = None
        changes: list[str] = []

        request = decision.get("check")
        if isinstance(request, dict):
            # 第二步：程序掷骰，再由模型写结局
            check_result = self._roll(action, request)
            outcome = self._ask_outcome(action, check_result)
            resolved = str(outcome.get("narration") or "").strip()
            if resolved:
                narration = resolved
            changes = self._apply_changes(outcome.get("state_changes"))

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

        return TurnResult(
            narration=narration,
            check=turn.check,
            changes=changes,
            turn=turn,
            over=self.state.over,
        )

    # ---------------- 与模型交互 ----------------
    def opening(self) -> str:
        """生成开场叙事。开新局时调用一次。

        开场是一段普通文本而不是 JSON——它没有结构化信息，只是把玩家带进情境。
        """
        messages = [
            {"role": "system", "content": prompts.OPENING_SYSTEM},
            {"role": "user", "content": prompts.build_context(self.state, recent_limit=0)},
        ]
        return self.client.chat(messages, temperature=config.GM_TEMPERATURE).strip()

    def _ask_action(self, action: str) -> dict:
        """第一步：让 GM 描写行动并决定是否检定。"""
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": f"玩家行动：{action}"},
        ]
        return self._ask_json(messages, temperature=config.GM_TEMPERATURE)

    def _ask_outcome(self, action: str, check: CheckResult) -> dict:
        """第二步：把掷骰结果告诉 GM，让它写结局。"""
        messages = [
            {"role": "system", "content": self._system_prompt()},
            {"role": "user", "content": prompts.build_resolve_prompt(action, check.describe())},
        ]
        return self._ask_json(messages, temperature=config.STRUCTURED_TEMPERATURE)

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
