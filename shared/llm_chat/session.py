"""对话上下文状态。

只维护「说过什么」，不关心由谁来展示。CLI 和后续的 Web 后端共用同一套
会话状态，各自决定如何呈现。
"""

from __future__ import annotations


class ConversationSession:
    """一次对话的上下文历史。"""

    def __init__(self, system_prompt: str = "") -> None:
        self.system_prompt = system_prompt
        self._history: list[dict] = []
        if system_prompt:
            self._history.append({"role": "system", "content": system_prompt})

    @property
    def messages(self) -> list[dict]:
        """当前完整上下文，可直接交给客户端发送。

        返回副本，避免调用方无意间改到内部状态。
        """
        return list(self._history)

    def add_user(self, text: str) -> None:
        """记录一条用户消息。"""
        self._history.append({"role": "user", "content": text})

    def add_assistant(self, text: str) -> None:
        """记录一条模型回复。"""
        self._history.append({"role": "assistant", "content": text})

    def drop_last(self) -> None:
        """丢弃最后一条消息。

        某一轮对话失败时用它回滚，避免半截内容留在上下文里污染后续对话。
        """
        if self._history and self._history[-1]["role"] != "system":
            self._history.pop()

    def clear(self) -> None:
        """清空对话上下文，只保留 system prompt。"""
        self._history = [message for message in self._history if message["role"] == "system"]
