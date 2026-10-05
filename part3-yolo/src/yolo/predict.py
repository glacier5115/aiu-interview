"""推理封装。

支持图片、目录、视频文件和摄像头（摄像头传设备号，例如 0）。
"""

from __future__ import annotations

from pathlib import Path

from . import config


def predict(
    weights: str | Path,
    source: str,
    conf: float = config.DEFAULT_CONF,
    device: str | None = None,
    save: bool = True,
    show: bool = False,
) -> list:
    """跑一次推理，返回 ultralytics 的结果列表。"""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    results = model.predict(
        source=source,
        conf=conf,
        device=device,
        save=save,
        show=show,
        project=str(config.RUNS_DIR),
        name="predict",
        exist_ok=True,
        verbose=False,
    )
    return list(results)


def describe(result) -> str:
    """把一张图的检测结果整理成一行字。"""
    names = result.names
    boxes = result.boxes
    if boxes is None or len(boxes) == 0:
        return "未检测到目标"

    counts: dict[str, int] = {}
    for class_id in boxes.cls.tolist():
        label = names[int(class_id)]
        counts[label] = counts.get(label, 0) + 1

    summary = "、".join(f"{name}×{count}" for name, count in sorted(counts.items()))
    return f"{len(boxes)} 个目标（{summary}）"


def speed_summary(result) -> str:
    """把 ultralytics 记录的耗时整理成人能读的一行。

    这是「实时推理」关心的数字：单帧总耗时决定了能达到多少 FPS。
    """
    speed = getattr(result, "speed", None)
    if not speed:
        return ""

    total_ms = sum(speed.values())
    fps = 1000 / total_ms if total_ms else 0
    parts = "  ".join(f"{stage} {value:.1f}ms" for stage, value in speed.items())
    return f"{parts}  →  合计 {total_ms:.1f}ms/帧，约 {fps:.0f} FPS"
