"""程序入口：只做组装，不放业务逻辑。

流程：解析命令行参数 → 组装客户端与会话 → 交给 CLI 交互层运行。

用法：
    python src/main.py
    python src/main.py --model qwen2.5-coder:1.5b
    python src/main.py --help
"""

from __future__ import annotations

import argparse
import sys

from llm_chat import config, repl
from llm_chat.client import OllamaClient
from llm_chat.session import ConversationSession


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="本地大模型 CLI 对话程序（通过 Ollama API 接入）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=config.DEFAULT_HOST,
        help=f"Ollama 服务地址（默认 {config.DEFAULT_HOST}）",
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"模型名（默认 {config.DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--system",
        default=config.DEFAULT_SYSTEM_PROMPT,
        help="system prompt（传空字符串可禁用）",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=config.DEFAULT_TEMPERATURE,
        help=f"采样温度（默认 {config.DEFAULT_TEMPERATURE}）",
    )
    parser.add_argument(
        "--think",
        action="store_true",
        help="开启思考模式。默认关闭：思考模型若不关闭，思考内容会占满输出配额",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """解析参数、组装各模块并启动。"""
    args = build_parser().parse_args(argv)

    client = OllamaClient(
        host=args.host,
        model=args.model,
        think=args.think,
        temperature=args.temperature,
    )
    session = ConversationSession(system_prompt=args.system)

    if not client.ping():
        print(f"[错误] 无法连接 Ollama（{args.host}）。")
        print("       请先启动服务：ollama serve")
        return 1

    try:
        repl.run(client, session)
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    # Windows 控制台在部分代码页下无法编码个别字符（例如 emoji），
    # 这里兜底替换掉不能编码的字符，避免整个程序因输出报错而中断
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
