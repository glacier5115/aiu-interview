"""CLI 视角的推理。

命令行要处理的不仅是单张图片，还有目录、视频和摄像头，并且需要保存标注图或
实时显示——这些是 ultralytics 的原生能力，直接用它。检测结果的**结构化转换**
则复用 shared/vision，保证命令行与 Web 后端对「一次检测」的理解是一致的。

核心检测逻辑在 shared/vision/detector.py；本模块只负责调用和呈现。
"""

from __future__ import annotations

from pathlib import Path

from shared.vision.detector import DetectionResult, result_from_ultralytics

from . import config


def run(
    weights: str | Path,
    source: str,
    conf: float = config.DEFAULT_CONF,
    device: str | None = None,
    save: bool = True,
    show: bool = False,
) -> list:
    """跑一次推理，返回 ultralytics 的原始结果列表。"""
    from ultralytics import YOLO

    model = YOLO(str(weights))
    return list(
        model.predict(
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
    )


def to_structured(raw_results: list) -> list[DetectionResult]:
    """把 ultralytics 的原始结果转成结构化结果。"""
    return [result_from_ultralytics(item) for item in raw_results]


def describe(result: DetectionResult) -> str:
    """把一张图的检测结果整理成一行字。"""
    if not result.detections:
        return "未检测到目标"
    summary = "、".join(
        f"{name}×{count}" for name, count in sorted(result.counts().items())
    )
    return f"{len(result.detections)} 个目标（{summary}）"


def speed_summary(raw_result) -> str:
    """把 ultralytics 记录的耗时整理成一行。

    这是「实时推理」关心的数字：单帧总耗时决定能达到多少 FPS。
    """
    speed = getattr(raw_result, "speed", None)
    if not speed:
        return ""

    total_ms = sum(speed.values())
    fps = 1000 / total_ms if total_ms else 0
    parts = "  ".join(f"{stage} {value:.1f}ms" for stage, value in speed.items())
    return f"{parts}  →  合计 {total_ms:.1f}ms/帧，约 {fps:.0f} FPS"
