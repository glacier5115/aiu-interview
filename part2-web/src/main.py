"""程序入口：只做组装，不放业务逻辑。

流程：解析命令行参数 → 组装模型客户端与会话仓库 → 交给 Web 应用 → 启动服务。

用法：
    python src/main.py
    python src/main.py --port 8080
    python src/main.py --model qwen2.5-coder:1.5b
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# 把仓库根目录加入导入路径，以便复用顶层 shared 包
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 第三方依赖清单，与 requirements.txt 保持一致
REQUIRED_PACKAGES = ("fastapi", "uvicorn", "requests")


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

import uvicorn  # noqa: E402  （须在依赖自检之后导入）

from server.app import create_app  # noqa: E402
from server.sessions import SessionStore  # noqa: E402
from shared.llm_chat import config  # noqa: E402
from shared.llm_chat.client import OllamaClient  # noqa: E402
from shared.vision.detector import Detector  # noqa: E402


def _build_detector(enabled: bool) -> Detector | None:
    """准备视觉检测器。

    检测是可选能力：没装 ultralytics、没有训练好的权重、显存不够，都不应该
    影响对话。所以这里把所有失败都收敛成「返回 None + 一句说明」。
    """
    if not enabled:
        print("视觉检测：已通过 --no-vision 关闭")
        return None

    if importlib.util.find_spec("ultralytics") is None:
        print("[提示] 未安装 ultralytics，视觉检测不可用")
        print("       需要的话：pip install -r ../part3-yolo/requirements.txt")
        return None

    detector = Detector()
    try:
        detector.load()
    except Exception as exc:  # noqa: BLE001  任何加载失败都只降级，不阻断服务
        print(f"[提示] 检测模型未就绪，视觉检测不可用：{exc}")
        return None

    try:
        # 第一次推理要几秒（CUDA 初始化与底层算法选型），放到启动阶段消化掉，
        # 免得第一个使用检测的人等在那里
        detector.warmup()
    except Exception as exc:  # noqa: BLE001
        print(f"[警告] 检测模型预热失败，首次检测会慢一些：{exc}")

    print(f"视觉检测：{detector.weights.name}")
    return detector


def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="本地大模型 Web 对话服务（FastAPI + SSE 流式推送）",
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
    parser.add_argument("--port", type=int, default=8000, help="监听端口（默认 8000）")
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
    parser.add_argument(
        "--no-vision",
        action="store_true",
        help="不加载 YOLO 检测模型。显存紧张或只做对话时可以加上",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """解析参数、组装各模块并启动服务。"""
    args = build_parser().parse_args(argv)

    client = OllamaClient(
        host=args.ollama,
        model=args.model,
        think=args.think,
        temperature=args.temperature,
    )

    if not client.ping():
        print(f"[错误] 无法连接 Ollama（{args.ollama}）。")
        print("       请先启动服务：ollama serve")
        return 1

    store = SessionStore(system_prompt=args.system)
    detector = _build_detector(enabled=not args.no_vision)
    app = create_app(client, store, detector)

    print(f"对话模型：{client.model}")
    print(f"Ollama：{client.host}")
    print(f"服务地址：http://{args.bind}:{args.port}")
    if args.bind != "127.0.0.1":
        print("[提醒] 已监听到非本机地址，同网段的设备都能访问此服务，且该服务没有鉴权")

    uvicorn.run(app, host=args.bind, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    # Windows 控制台在部分代码页下无法编码个别字符（例如 emoji），
    # 这里兜底替换掉不能编码的字符，避免程序因输出报错而中断
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
