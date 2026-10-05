"""视觉部分的默认配置。"""

from __future__ import annotations

from pathlib import Path

# 本目录是 shared/vision/，往上两级是仓库根
REPO_ROOT = Path(__file__).resolve().parents[2]

# Part 3 训练产出的权重。可以用参数覆盖成别的模型。
DEFAULT_WEIGHTS = REPO_ROOT / "part3-yolo" / "runs" / "coco128_yolo11n" / "weights" / "best.pt"

# 置信度阈值：低于它的框不返回
DEFAULT_CONF = 0.25
