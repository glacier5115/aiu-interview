"""会话仓库：按 session_id 存放对话上下文。

本地单人使用，会话只存在内存里，进程重启即清空，不做持久化。
"""

from __future__ import annotations

import threading

from shared.llm_chat.session import ConversationSession


class SessionStore:
    """session_id 到对话上下文的映射。

    前端在浏览器本地保存自己的 session_id，后端据此找回对应的上下文，
    因此同一个服务可以同时服务多个标签页而互不干扰。
    """

    def __init__(self, system_prompt: str = "") -> None:
        self._system_prompt = system_prompt
        self._sessions: dict[str, ConversationSession] = {}
        self._guard = threading.Lock()

    def get(self, session_id: str) -> ConversationSession:
        """取出会话；不存在则按 system prompt 新建一个。"""
        with self._guard:
            if session_id not in self._sessions:
                self._sessions[session_id] = ConversationSession(self._system_prompt)
            return self._sessions[session_id]

    def reset(self, session_id: str) -> None:
        """丢弃会话，下次访问会拿到一个全新的上下文。"""
        with self._guard:
            self._sessions.pop(session_id, None)

    def count(self) -> int:
        """当前持有的会话数量。"""
        with self._guard:
            return len(self._sessions)
