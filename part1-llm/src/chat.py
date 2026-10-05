#!/usr/bin/env python3
"""本地大模型 CLI 对话程序。

通过 Ollama 的 HTTP API 接入本地模型，支持多轮流式对话。

用法示例：
    python src/chat.py
    python src/chat.py --model qwen2.5-coder:1.5b
    python src/chat.py --help
"""

from __future__ import annotations

import argparse
import json
import re
import sys

import requests

DEFAULT_HOST = "http://127.0.0.1:11434"

# 模型输出的文本会被直接打到终端上。如果其中带 ANSI 转义序列
# （例如被诱导复述了一段含 ESC 的内容），就可能操纵终端显示效果，
# 因此显示前统一过滤掉，只保留换行和制表符。
_TERMINAL_ESCAPE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"               # CSI 序列
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"    # OSC 序列
    r"|\x1b[@-Z\\-_]"                        # 其他两字节转义
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"    # 控制字符（保留 \t \n \r）
)


def sanitize_for_terminal(text: str) -> str:
    """过滤掉可能操纵终端显示的转义序列。

    只作用于显示，存进对话上下文的仍然是模型返回的原文。
    """
    return _TERMINAL_ESCAPE.sub("", text)
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_SYSTEM = "你是一个乐于助人的中文助手，回答简洁、准确。"

HELP_TEXT = """可用命令：
  /help            显示本帮助
  /clear           清空对话上下文（保留 system prompt）
  /model [名称]    切换模型；不带名称时列出本机可用模型
  /exit            退出程序（/quit、/q 同效）
"""

# 连接超时 5 秒；读取超时放宽到 5 分钟，给模型加载和长回复留余量
TIMEOUT = (5, 300)


class OllamaError(RuntimeError):
    """面向用户的错误，信息可直接展示在终端里。"""


class OllamaClient:
    """对 Ollama /api/chat 的极薄封装，只做一件事：把模型回复流式吐出来。"""

    def __init__(self, host: str, model: str, think: bool = False, temperature: float = 0.7) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.think = think
        self.temperature = temperature

    def ping(self) -> bool:
        """确认 Ollama 服务可达。"""
        try:
            requests.get(f"{self.host}/api/tags", timeout=5).raise_for_status()
            return True
        except requests.exceptions.RequestException:
            return False

    def list_models(self) -> list[str]:
        """返回本机已下载的模型名列表。"""
        try:
            resp = requests.get(f"{self.host}/api/tags", timeout=5)
            resp.raise_for_status()
        except requests.exceptions.RequestException as exc:
            raise OllamaError(f"无法获取模型列表：{exc}") from exc
        try:
            models = resp.json().get("models", [])
        except ValueError as exc:
            raise OllamaError("无法解析模型列表响应：服务端返回的不是合法 JSON") from exc
        return [item["name"] for item in models]

    def chat_stream(self, messages: list[dict]):
        """逐块产出模型回复的文本增量。

        这里使用 Ollama 原生接口而不是 OpenAI 兼容接口，原因是原生接口的
        ``think`` 参数可以可靠地关闭思考模式；在 /v1/chat/completions 上
        同样的参数会被忽略，导致正文被思考内容占满。
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
                f"{self.host}/api/chat", json=payload, stream=True, timeout=TIMEOUT
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
                # iter_lines 在流式响应下按行切分，正好对应一行一个 JSON 对象的 NDJSON 格式，
                # 保持 bytes 不预先解码，交给 json.loads 按 UTF-8 处理，避免中文乱码
                if not raw_line:
                    continue
                try:
                    chunk = json.loads(raw_line)
                except json.JSONDecodeError as exc:
                    raise OllamaError(f"服务端返回了无法解析的数据：{raw_line[:120]!r}") from exc
                if not isinstance(chunk, dict):
                    continue
                if chunk.get("error"):
                    raise OllamaError(chunk["error"])
                piece = chunk.get("message", {}).get("content") or ""
                if piece:
                    yield piece
                if chunk.get("done"):
                    return


def handle_command(line: str, client: OllamaClient, history: list[dict]) -> str:
    """处理以 / 开头的命令，返回 "exit" 表示要退出程序。"""
    command, _, argument = line[1:].partition(" ")
    command = command.lower()
    argument = argument.strip()

    if command in ("exit", "quit", "q"):
        return "exit"

    if command == "clear":
        history[:] = [message for message in history if message["role"] == "system"]
        print("[已清空对话上下文]\n")

    elif command == "model":
        if argument:
            client.model = argument
            print(f"[已切换模型：{argument}]\n")
        else:
            try:
                names = client.list_models()
            except OllamaError as exc:
                print(f"[错误] {exc}\n")
            else:
                print("本机可用模型：")
                for name in names:
                    marker = "*" if name == client.model else " "
                    print(f"  {marker} {name}")
                print()

    elif command == "help":
        print(HELP_TEXT)

    else:
        print(f"未知命令 /{command}，输入 /help 查看可用命令\n")

    return "ok"


def run_repl(client: OllamaClient, system_prompt: str) -> None:
    """交互式对话主循环。"""
    history: list[dict] = []
    if system_prompt:
        history.append({"role": "system", "content": system_prompt})

    print(f"已连接 {client.host}，当前模型 {client.model}")
    print("输入 /help 查看命令，/exit 退出\n")

    while True:
        try:
            user_input = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return

        if not user_input:
            continue

        if user_input.startswith("/"):
            if handle_command(user_input, client, history) == "exit":
                return
            continue

        history.append({"role": "user", "content": user_input})
        print(f"{client.model} > ", end="", flush=True)

        pieces: list[str] = []
        try:
            for piece in client.chat_stream(history):
                pieces.append(piece)
                # 显示时过滤转义序列，存进上下文的仍是模型返回的原文
                print(sanitize_for_terminal(piece), end="", flush=True)
        except OllamaError as exc:
            print(f"\n[错误] {exc}\n")
            history.pop()  # 这一轮没成功，不要留在上下文里污染后续对话
            continue
        except KeyboardInterrupt:
            print("\n[已中断本轮回复]\n")
            history.pop()
            continue

        if not pieces:
            print("\n[警告] 模型没有返回正文。可能是思考内容占满了输出配额，"
                  "可加 --think 参数观察完整思考过程。\n")
            history.pop()
            continue

        print("\n")
        history.append({"role": "assistant", "content": "".join(pieces)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="本地大模型 CLI 对话程序（通过 Ollama API 接入）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--host", default=DEFAULT_HOST, help=f"Ollama 服务地址（默认 {DEFAULT_HOST}）")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"模型名（默认 {DEFAULT_MODEL}）")
    parser.add_argument("--system", default=DEFAULT_SYSTEM, help="system prompt（传空字符串可禁用）")
    parser.add_argument("--temperature", type=float, default=0.7, help="采样温度（默认 0.7）")
    parser.add_argument(
        "--think",
        action="store_true",
        help="开启思考模式。默认关闭：Qwen3 等思考模型若不关闭，思考内容会占满输出配额",
    )
    args = parser.parse_args(argv)

    client = OllamaClient(
        host=args.host,
        model=args.model,
        think=args.think,
        temperature=args.temperature,
    )

    if not client.ping():
        print(f"[错误] 无法连接 Ollama（{args.host}）。")
        print("       请先启动服务：ollama serve")
        return 1

    try:
        run_repl(client, args.system)
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    # Windows 控制台在部分代码页下无法编码个别字符（例如 emoji），
    # 这里只兜底替换掉不能编码的字符，避免整个程序因输出报错而中断
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
