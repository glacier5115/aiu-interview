"""与本地 Ollama 服务通信的客户端。

职责边界：只做协议层的事——发请求、解析流式响应、按顺序产出文本块。
这里不出现任何终端渲染或交互代码，因此 CLI（``repl.py``）和后续的
Web 后端可以共用同一个客户端。
"""

from __future__ import annotations

import json
from typing import Iterator

import requests

from .config import PROBE_TIMEOUT, REQUEST_TIMEOUT


class OllamaError(RuntimeError):
    """面向用户的错误，消息可以直接展示给使用者。"""


class OllamaClient:
    """对 Ollama ``/api/chat`` 的薄封装：把模型回复按块产出。

    采用 Ollama 原生接口而不是 ``/v1/chat/completions``，原因是 ``think``
    参数只有在原生接口上才能可靠关闭思考模式；走兼容接口的话，思考内容
    会占满输出配额，导致正文为空。
    """

    def __init__(
        self,
        host: str,
        model: str,
        think: bool = False,
        temperature: float = 0.7,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.think = think
        self.temperature = temperature

    def ping(self) -> bool:
        """探测服务是否可达。不抛异常，只返回布尔值。"""
        try:
            requests.get(f"{self.host}/api/tags", timeout=PROBE_TIMEOUT).raise_for_status()
            return True
        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> list[str]:
        """返回本机已下载的模型名列表。"""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=PROBE_TIMEOUT)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise OllamaError(f"无法获取模型列表：{exc}") from exc

        try:
            models = resp.json().get("models", [])
        except ValueError as exc:
            raise OllamaError("无法解析模型列表响应：服务端返回的不是合法 JSON") from exc
        return [item["name"] for item in models]

    def chat(
        self,
        messages: list[dict],
        *,
        json_mode: bool = False,
        temperature: float | None = None,
    ) -> str:
        """一次性的非流式调用，返回完整回复。

        json_mode 会要求 Ollama 强制输出合法 JSON（原生接口的 format 参数）。
        这类场景不适合流式——JSON 得完整拿到才能解析。

        temperature 可以单独覆盖：叙事希望有点想象力，结构化输出则越稳越好。
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "think": self.think,
            "options": {
                "temperature": self.temperature if temperature is None else temperature
            },
        }
        if json_mode:
            payload["format"] = "json"

        try:
            resp = requests.post(
                f"{self.host}/api/chat", json=payload, timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.RequestException as exc:
            raise OllamaError(
                f"无法连接 Ollama（{self.host}）。请确认服务已启动：ollama serve"
            ) from exc

        if resp.status_code == 404:
            raise OllamaError(
                f"模型 {self.model} 不存在。可用 /model 查看本机模型，"
                f"或执行 ollama pull {self.model} 下载"
            )
        if not resp.ok:
            raise OllamaError(f"请求失败（HTTP {resp.status_code}）：{resp.text[:200]}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise OllamaError("服务端返回的不是合法 JSON") from exc

        if data.get("error"):
            raise OllamaError(data["error"])
        return data.get("message", {}).get("content") or ""

    def chat_stream(self, messages: list[dict]) -> Iterator[str]:
        """按块产出模型回复的文本增量。

        这是纯数据接口：产出的是模型原文。任何展示层的处理（例如终端
        转义序列过滤）都由调用方在渲染时完成，本方法不参与。
        """
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "think": self.think,
            "options": {"temperature": self.temperature},
        }

        try:
            resp = requests.post(
                f"{self.host}/api/chat", json=payload, stream=True, timeout=REQUEST_TIMEOUT
            )
        except requests.exceptions.RequestException as exc:
            raise OllamaError(
                f"无法连接 Ollama（{self.host}）。请确认服务已启动：ollama serve"
            ) from exc

        with resp:
            if resp.status_code == 404:
                raise OllamaError(
                    f"模型 {self.model} 不存在。可用 /model 查看本机模型，"
                    f"或执行 ollama pull {self.model} 下载"
                )
            if not resp.ok:
                raise OllamaError(f"请求失败（HTTP {resp.status_code}）：{resp.text[:200]}")

            for raw_line in resp.iter_lines():
                # 流式响应是「一行一个 JSON 对象」的 NDJSON 格式，正好按行切分。
                # 保持 bytes 不预先解码，交给 json.loads 按 UTF-8 处理，避免中文乱码。
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise OllamaError(
                        f"服务端返回了无法解析的数据：{raw_line[:120]!r}"
                    ) from exc
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("error"):
                    raise OllamaError(chunk["error"])

                piece = chunk.get("message", {}).get("content") or ""
                if piece:
                    yield piece
                if chunk.get("done"):
                    return
