"""Part 3 的默认配置与路径。

所有默认值集中在这里，训练脚本、推理脚本、资源下载都从这里取。
"""

from __future__ import annotations

from pathlib import Path

# 本目录是 part3-yolo/src/yolo/，往上三级就是 part3-yolo/
PROJECT_ROOT = Path(__file__).resolve().parents[2]

DATASETS_DIR = PROJECT_ROOT / "datasets"
WEIGHTS_DIR = PROJECT_ROOT / "weights"
RUNS_DIR = PROJECT_ROOT / "runs"

# ---------- 数据集 ----------
# coco128：ultralytics 官方的迷你数据集，128 张图，用来验证训练流程能否跑通，
# 不是为了训出可用的模型。体积用于校验下载是否完整（见 assets.py）。
COCO128_URL = "https://ultralytics.com/assets/coco128.zip"
COCO128_SIZE = 6983030
COCO128_DIR = DATASETS_DIR / "coco128"
COCO128_YAML = COCO128_DIR / "coco128.yaml"

# ---------- 预训练权重 ----------
# 按顺序尝试，第一个不通就换下一个（本机到 GitHub 的连接不稳定）
PRETRAINED_PATH = WEIGHTS_DIR / "yolo11n.pt"
PRETRAINED_SIZE = 5613764
PRETRAINED_SOURCES = (
    "https://github.com/ultralytics/assets/releases/download/v8.3.0/yolo11n.pt",
    "https://hf-mirror.com/Ultralytics/YOLO11/resolve/main/yolo11n.pt",
)

# ---------- 训练默认值 ----------
# 8GB 显存下的保守配置：小模型 + 较小批大小，先保证能跑通
DEFAULT_MODEL = str(PRETRAINED_PATH)
DEFAULT_EPOCHS = 50
DEFAULT_IMGSZ = 640
DEFAULT_BATCH = 16
RUN_NAME = "coco128_yolo11n"

# ---------- 推理默认值 ----------
DEFAULT_CONF = 0.25
