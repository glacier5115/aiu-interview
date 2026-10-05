"""程序入口：只做组装，不放业务逻辑。

流程：解析命令行参数 → 组装客户端与会话 → 交给 CLI 交互层运行。

用法：
    python src/main.py
    python src/main.py --model qwen2.5-coder:1.5b
    python src/main.py --help
"""

from __future__ import annotations

import argparse
import importlib.util
import sys

# 第三方依赖清单，与 requirements.txt 保持一致
REQUIRED_PACKAGES = ("requests",)


def _check_dependencies() -> None:
    """启动前的环境自检。

    缺依赖时给出可操作的提示，而不是甩一个 ModuleNotFoundError 的 traceback。
    最常见的成因是 ``python`` 落到了系统自带的解释器上，而不是项目的 conda 环境。
    """
    missing = [name for name in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None]
    if not missing:
        return

    print(f"[错误] 当前 Python 环境缺少依赖：{', '.join(missing)}")
    print(f"       正在使用的解释器：{sys.executable}")
    print("       本项目需要 conda 环境 ai_project（Python 3.10），请先执行：")
    print("           conda activate ai_project")
    print("           pip install -r requirements.txt")
    print("           python src/main.py")
    print("       如果提示找不到 conda 命令，先执行一次 conda init 并重开终端")
    print("       （PowerShell 用 conda init powershell，cmd 用 conda init cmd.exe）；")
    print("       也可以直接用该环境的 python 解释器来运行本文件。")
    raise SystemExit(1)


_check_dependencies()

from llm_chat import config, repl  # noqa: E402  （须在依赖自检之后导入）
from llm_chat.client import OllamaClient  # noqa: E402
from llm_chat.session import ConversationSession  # noqa: E402


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
