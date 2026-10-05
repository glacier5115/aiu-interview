"""目标检测：加载 YOLO 模型，对图片推理，产出结构化结果。

这是「视觉」部分的公共核心，被 Part 3 的命令行与 Part 2 的 Web 后端共用。
它刻意不产出任何面向人的文本：结果统一是 Detection 列表，怎么呈现由各自的
展示层决定——CLI 打成文字，Web 转成 JSON 交给前端画框。

模型加载与首次推理都有一次性开销（CUDA 初始化、底层算法选型，实测约 4 秒），
所以提供 warmup()，让服务在启动阶段把它消化掉，而不是让第一个用户的请求等。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import DEFAULT_CONF, DEFAULT_WEIGHTS


@dataclass(frozen=True)
class Detection:
    """一个检测框。坐标是原图像素坐标，左上角为原点。"""

    label: str
    confidence: float
    x1: int
    y1: int
    x2: int
    y2: int

    def to_dict(self) -> dict[str, Any]:
        """转成可直接 JSON 序列化的结构。"""
        return {
            "label": self.label,
            "confidence": round(self.confidence, 4),
            "box": [self.x1, self.y1, self.x2, self.y2],
        }


@dataclass(frozen=True)
class DetectionResult:
    """一张图的检测结果。"""

    detections: list[Detection]
    width: int
    height: int
    elapsed_ms: float

    def to_dict(self) -> dict[str, Any]:
        """转成可直接 JSON 序列化的结构。"""
        return {
            "width": self.width,
            "height": self.height,
            "elapsed_ms": round(self.elapsed_ms, 1),
            "detections": [item.to_dict() for item in self.detections],
        }

    def counts(self) -> dict[str, int]:
        """按类别汇总数量，便于只关心「有哪些东西」的场景。"""
        summary: dict[str, int] = {}
        for item in self.detections:
            summary[item.label] = summary.get(item.label, 0) + 1
        return summary


class Detector:
    """YOLO 检测器。创建一次、反复使用，模型只在首次使用时加载。"""

    def __init__(
        self,
        weights: Path | str = DEFAULT_WEIGHTS,
        conf: float = DEFAULT_CONF,
        device: int | str | None = 0,
    ) -> None:
        self.weights = Path(weights)
        self.conf = conf
        self.device = device
        self._model = None

    @property
    def ready(self) -> bool:
        """模型是否已加载。"""
        return self._model is not None

    def load(self) -> None:
        """加载模型。可重复调用，只有第一次真正做事。"""
        if self._model is not None:
            return

        if not self.weights.exists():
            raise FileNotFoundError(
                f"找不到权重文件：{self.weights}\n"
                "请先在 part3-yolo 目录下跑一次训练：python src/main.py train"
            )

        # ultralytics 的导入本身就要一两秒，放在方法里可以避免只跑对话时白等
        from ultralytics import YOLO

        self._model = YOLO(str(self.weights))

    def warmup(self) -> None:
        """用一张空白图先推理一次。

        第一次推理要几秒（CUDA 初始化与底层算法选型），把它提前到启动阶段，
        之后用户的第一次检测就是正常速度。
        """
        try:
            import numpy as np
        except ImportError:  # pragma: no cover - numpy 是 ultralytics 的依赖，正常都在
            return

        self.load()
        blank = np.zeros((640, 640, 3), dtype="uint8")
        self._model.predict(source=blank, conf=self.conf, device=self.device, verbose=False)

    def detect(self, image: Any) -> DetectionResult:
        """对一张图片做检测。

        image 可以是文件路径、PIL 图像或 numpy 数组。
        """
        self.load()

        started = time.perf_counter()
        results = self._model.predict(
            source=image, conf=self.conf, device=self.device, verbose=False
        )
        elapsed_ms = (time.perf_counter() - started) * 1000

        return result_from_ultralytics(results[0], elapsed_ms=elapsed_ms)


def result_from_ultralytics(raw: Any, *, elapsed_ms: float = 0.0) -> DetectionResult:
    """把 ultralytics 的 Results 转成结构化的 DetectionResult。

    单独抽成函数，是为了让命令行也能复用：CLI 需要保存标注图、实时显示、
    处理视频和摄像头，这些必须直接用 ultralytics 的原生 predict，但结果的
    结构化转换应当和 Web 后端保持一致。
    """
    height, width = int(raw.orig_shape[0]), int(raw.orig_shape[1])

    boxes = raw.boxes
    detections: list[Detection] = []
    if boxes is not None and len(boxes) > 0:
        for (x1, y1, x2, y2), confidence, class_id in zip(
            boxes.xyxy.tolist(), boxes.conf.tolist(), boxes.cls.tolist()
        ):
            detections.append(
                Detection(
                    label=str(raw.names[int(class_id)]),
                    confidence=float(confidence),
                    x1=int(x1),
                    y1=int(y1),
                    x2=int(x2),
                    y2=int(y2),
                )
            )

    return DetectionResult(
        detections=detections, width=width, height=height, elapsed_ms=elapsed_ms
    )
