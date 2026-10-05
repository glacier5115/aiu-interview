"""程序入口：只做组装，不放业务逻辑。

流程：解析命令行参数 → 组装模型客户端与对局仓库 → 交给 Web 应用 → 启动服务。

用法：
    python src/main.py
    python src/main.py --port 8100
    python src/main.py --model qwen2.5-coder:1.5b
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# 把仓库根目录加入导入路径，以便复用顶层 shared 包（LLM 客户端在那里）
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 第三方依赖清单，与 requirements.txt 保持一致
REQUIRED_PACKAGES = ("fastapi", "uvicorn", "requests")


def _check_dependencies() -> None:
    """启动前的环境自检。

    缺依赖时给出可操作的提示，而不是甩一个 ModuleNotFoundError 的 traceback。
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
    print("       （PowerShell 用 conda init powershell，cmd 用 conda init cmd.exe）。")
    raise SystemExit(1)


_check_dependencies()

import uvicorn  # noqa: E402  （须在依赖自检之后导入）

from server.app import create_app  # noqa: E402
from server.games import GameStore  # noqa: E402
from shared.llm_chat import config  # noqa: E402
from shared.llm_chat.client import OllamaClient  # noqa: E402


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="AI GM 跑团服务（本地大模型当主持人）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--ollama",
        default=config.DEFAULT_HOST,
        help=f"Ollama 服务地址（默认 {config.DEFAULT_HOST}）",
    )
    parser.add_argument(
        "--model",
        default=config.DEFAULT_MODEL,
        help=f"模型名（默认 {config.DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--bind",
        default="127.0.0.1",
        help="监听地址。默认只监听本机；改成 0.0.0.0 会让同网段的设备都能访问",
    )
    parser.add_argument("--port", type=int, default=8100, help="监听端口（默认 8100）")
    return parser


def main(argv: list[str] | None = None) -> int:
    """解析参数、组装各模块并启动服务。"""
    args = build_parser().parse_args(argv)

    client = OllamaClient(host=args.ollama, model=args.model)

    if not client.ping():
        print(f"[错误] 无法连接 Ollama（{args.ollama}）。")
        print("       请先启动服务：ollama serve")
        return 1

    store = GameStore(client)
    app = create_app(client, store)

    print(f"GM 模型：{client.model}")
    print(f"Ollama：{client.host}")
    print(f"服务地址：http://{args.bind}:{args.port}")
    if args.bind != "127.0.0.1":
        print("[提醒] 已监听到非本机地址，同网段的设备都能访问此服务，且该服务没有鉴权")

    uvicorn.run(app, host=args.bind, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
