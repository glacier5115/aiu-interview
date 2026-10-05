"""Part 3 入口：子命令分发。

只做参数解析与模块组装，具体干活的代码在 yolo 包里。

    python src/main.py check                       检查环境与 GPU
    python src/main.py dataset                     下载并准备 coco128
    python src/main.py train                       训练（默认 yolo11n + coco128）
    python src/main.py train --epochs 100 --batch 8
    python src/main.py predict --source some.jpg   对图片推理
    python src/main.py predict --source 0          调用摄像头
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

# 把仓库根目录加入导入路径，以便复用顶层 shared 包（视觉推理的核心在那里）
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 第三方依赖清单，与 requirements.txt 保持一致
REQUIRED_PACKAGES = ("torch", "ultralytics")


def _check_dependencies() -> None:
    """启动前的环境自检。

    缺依赖时给出可操作的提示，而不是甩一个 ModuleNotFoundError 的 traceback。
    """
    missing = [name for name in REQUIRED_PACKAGES if importlib.util.find_spec(name) is None]
    if not missing:
        return

    print(f"[错误] 当前 Python 环境缺少依赖：{', '.join(missing)}")
    print(f"       正在使用的解释器：{sys.executable}")
    print("       本项目需要 conda 环境 ai_project（Python 3.10）：")
    print("           conda activate ai_project")
    print("           pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128")
    print("           pip install -r requirements.txt")
    print("       注意 torch 必须从 PyTorch 官方源装 CUDA 版本，走默认 PyPI 会是 CPU 版。")
    raise SystemExit(1)


_check_dependencies()

from yolo import config  # noqa: E402  （须在依赖自检之后导入）


def _configure_ultralytics() -> None:
    """关掉 ultralytics 默认开启的匿名使用数据上报。

    它默认会把运行环境的统计信息发回官方，与项目无关，这里主动关掉。
    """
    from ultralytics import settings

    if settings.get("sync"):
        settings.update({"sync": False})


DEFAULT_WEIGHTS = config.RUNS_DIR / config.RUN_NAME / "weights" / "best.pt"


# ---------------- 子命令 ----------------
def cmd_check(_args: argparse.Namespace) -> int:
    """打印环境信息，确认 GPU 真的能用。"""
    import platform

    import torch

    print(f"Python      {platform.python_version()} ({platform.machine()})")
    print(f"torch       {torch.__version__}")
    print(f"CUDA 版本    {torch.version.cuda}")

    available = torch.cuda.is_available()
    print(f"CUDA 可用    {available}")
    if not available:
        print("\n[警告] torch 看不到 GPU。常见原因：装成了 CPU 版，或显卡驱动过旧。")
        return 1

    index = torch.cuda.current_device()
    capability = torch.cuda.get_device_capability(index)
    total_gb = torch.cuda.get_device_properties(index).total_memory / 1024**3
    print(f"设备        {torch.cuda.get_device_name(index)}")
    print(f"算力        sm_{capability[0]}{capability[1]}  (需要 >= sm_120 才说明装对了 Blackwell 版本)")
    print(f"显存        {total_gb:.1f} GB")
    return 0


def cmd_dataset(args: argparse.Namespace) -> int:
    """下载并准备数据集。"""
    from yolo import dataset

    path = dataset.ensure_coco128(force=args.force)
    print(f"\n数据集配置：{path}")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    """训练。"""
    from yolo import assets, dataset, train

    if args.model == config.DEFAULT_MODEL:
        assets.ensure_pretrained_weights()

    data = dataset.ensure_coco128()
    run_dir = train.train(
        data=str(data),
        model=args.model,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        name=args.name,
    )

    metrics = train.read_final_metrics(run_dir)
    if metrics:
        print("\n最后一轮的指标：")
        for label, value in metrics.items():
            print(f"  {label:10} {value}")

    print(f"\n权重：{run_dir / 'weights' / 'best.pt'}")
    print(f"曲线：{run_dir / 'results.png'}")
    return 0


def cmd_predict(args: argparse.Namespace) -> int:
    """推理。"""
    from yolo import predict

    weights = Path(args.weights)
    if not weights.exists():
        print(f"[错误] 找不到权重文件：{weights}")
        print("       先跑一次训练，或指定已有权重：--weights path/to/best.pt")
        return 1

    print(f"权重：{weights}")
    print(f"输入：{args.source}")
    raw_results = predict.run(
        weights=weights,
        source=args.source,
        conf=args.conf,
        device=args.device,
        save=not args.no_save,
        show=args.show,
    )
    structured = predict.to_structured(raw_results)

    print(f"\n共处理 {len(structured)} 帧/张，前几个结果：")
    for raw_item, item in list(zip(raw_results, structured))[:5]:
        print(f"  {Path(raw_item.path).name}：{predict.describe(item)}")
    if len(structured) > 5:
        print("  ……（其余省略）")

    if raw_results:
        print(f"\n耗时：{predict.speed_summary(raw_results[0])}")
    if not args.no_save:
        print(f"标注结果保存在：{config.RUNS_DIR / 'predict'}")
    return 0


# ---------------- 参数 ----------------
def build_parser() -> argparse.ArgumentParser:
    """构造命令行参数解析器。"""
    parser = argparse.ArgumentParser(
        description="YOLO 训练与推理（基于 ultralytics）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("check", help="检查环境与 GPU 是否就绪")

    dataset_parser = subparsers.add_parser("dataset", help="准备 coco128 数据集")
    dataset_parser.add_argument("--force", action="store_true", help="重新下载，覆盖已存在的数据集")

    train_parser = subparsers.add_parser("train", help="训练模型")
    train_parser.add_argument("--model", default=config.DEFAULT_MODEL, help=f"模型（默认 {config.DEFAULT_MODEL}）")
    train_parser.add_argument("--epochs", type=int, default=config.DEFAULT_EPOCHS, help="训练轮数")
    train_parser.add_argument("--imgsz", type=int, default=config.DEFAULT_IMGSZ, help="输入尺寸")
    train_parser.add_argument("--batch", type=int, default=config.DEFAULT_BATCH, help="批大小，显存不够就调小")
    train_parser.add_argument("--device", default=None, help="设备，例如 0 表示第一块 GPU；不填则自动选择")
    train_parser.add_argument("--name", default=config.RUN_NAME, help="产物目录名")

    predict_parser = subparsers.add_parser("predict", help="用训练好的权重推理")
    predict_parser.add_argument("--weights", default=str(DEFAULT_WEIGHTS), help="权重文件路径")
    predict_parser.add_argument("--source", required=True, help="图片/目录/视频路径，或摄像头编号（如 0）")
    predict_parser.add_argument("--conf", type=float, default=config.DEFAULT_CONF, help="置信度阈值")
    predict_parser.add_argument("--device", default=None, help="设备，例如 0 表示第一块 GPU")
    predict_parser.add_argument("--no-save", action="store_true", help="不保存标注后的图片")
    predict_parser.add_argument("--show", action="store_true", help="弹窗实时显示（摄像头场景）")

    return parser


def main(argv: list[str] | None = None) -> int:
    """解析参数并分发给对应的子命令。"""
    args = build_parser().parse_args(argv)

    handlers = {
        "check": cmd_check,
        "dataset": cmd_dataset,
        "train": cmd_train,
        "predict": cmd_predict,
    }
    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        print("\n已中断")
        return 130


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    raise SystemExit(main())
