"""训练封装。

对 ultralytics 的调用集中在这里，命令行参数由 main.py 组装后传进来。
"""

from __future__ import annotations

import csv
from pathlib import Path

from . import config

# results.csv 里我们关心的列
_METRIC_COLUMNS = {
    "epoch": "epoch",
    "metrics/precision(B)": "precision",
    "metrics/recall(B)": "recall",
    "metrics/mAP50(B)": "mAP50",
    "metrics/mAP50-95(B)": "mAP50-95",
}


def train(
    data: str,
    model: str = config.DEFAULT_MODEL,
    epochs: int = config.DEFAULT_EPOCHS,
    imgsz: int = config.DEFAULT_IMGSZ,
    batch: int = config.DEFAULT_BATCH,
    device: str | None = None,
    name: str = config.RUN_NAME,
) -> Path:
    """跑一次训练，返回产物目录。

    首次运行会自动下载预训练权重（yolo11n.pt 约 5MB）。
    """
    from ultralytics import YOLO

    print(f"模型：{model}")
    print(f"数据集：{data}")
    print(f"轮数：{epochs}  图像尺寸：{imgsz}  批大小：{batch}  设备：{device or '自动'}")
    print("-" * 56)

    yolo = YOLO(model)
    yolo.train(
        data=data,
        epochs=epochs,
        imgsz=imgsz,
        batch=batch,
        device=device,
        project=str(config.RUNS_DIR),
        name=name,
        exist_ok=True,  # 允许覆盖同名目录，避免反复训练堆积一堆 runs
    )

    run_dir = config.RUNS_DIR / name
    print("-" * 56)
    print(f"训练完成，产物目录：{run_dir}")
    return run_dir


def read_final_metrics(run_dir: Path) -> dict:
    """从 results.csv 里读出最后一轮的指标。

    比从内存里的对象取更稳：训练中断后重新读文件也能拿到，格式也不随
    ultralytics 的返回类型变化。
    """
    csv_path = Path(run_dir) / "results.csv"
    if not csv_path.exists():
        return {}

    with csv_path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return {}

    last = rows[-1]
    return {
        label: _format(last.get(column, "")).strip()
        for column, label in _METRIC_COLUMNS.items()
    }


def _format(raw: str) -> str:
    """把 csv 里的数值整理成好读的形式。"""
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return str(raw)
    return f"{value:.4f}" if value < 1 else f"{int(value)}"
