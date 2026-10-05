"""数据集准备。

下载 coco128 —— ultralytics 官方的迷你数据集（128 张图，约 7MB）。它的作用是
验证训练流程能跑通，不是为了训出可用的模型。

数据集放在 part3-yolo/datasets/ 下（已被 .gitignore 忽略），并由本模块生成一个
指向该目录的 yaml。之所以不直接用 ultralytics 内置的 coco128.yaml，是因为那样
数据集会被下载到它自己的全局设置目录里，位置不由项目控制。
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from . import assets
from .config import COCO128_DIR, COCO128_SIZE, COCO128_URL, COCO128_YAML, DATASETS_DIR

_IMAGES_DIR = COCO128_DIR / "images" / "train2017"


def ensure_coco128(*, force: bool = False) -> Path:
    """确保 coco128 与对应的 yaml 都已就绪，返回可交给 ultralytics 的 yaml 路径。"""
    if not force and _IMAGES_DIR.exists():
        print(f"数据集已存在：{COCO128_DIR}")
    else:
        _download_and_extract()

    _write_dataset_yaml()
    return COCO128_YAML


def _download_and_extract() -> None:
    """下载并解压 coco128。"""
    DATASETS_DIR.mkdir(parents=True, exist_ok=True)
    archive = DATASETS_DIR / "coco128.zip"

    print("正在下载 coco128（约 7MB）……")
    # 体积已知，下载中断会自动续传重试，见 assets.download
    assets.download(COCO128_URL, archive, expected_size=COCO128_SIZE, retries=6)
    print(f"  已下载：{archive}")

    print("正在解压……")
    with zipfile.ZipFile(archive) as handle:
        handle.extractall(DATASETS_DIR)
    archive.unlink(missing_ok=True)

    if not _IMAGES_DIR.exists():
        raise RuntimeError(f"解压后没有找到图片目录 {_IMAGES_DIR}，数据集结构可能与预期不一致")
    print(f"  完成，图片目录：{_IMAGES_DIR}")


def _builtin_yaml() -> Path:
    """定位 ultralytics 内置的 coco128.yaml。"""
    import ultralytics

    path = Path(ultralytics.__file__).parent / "cfg" / "datasets" / "coco128.yaml"
    if not path.exists():
        raise RuntimeError(f"找不到 ultralytics 内置的 coco128.yaml：{path}")
    return path


def _write_dataset_yaml() -> None:
    """生成指向本地数据集的 yaml。

    类别表直接从 ultralytics 内置的 coco128.yaml 抄过来，只把 path 换成绝对路径，
    因此不依赖 ultralytics 的全局 datasets_dir 设置，数据集放哪完全由项目决定。
    """
    import yaml

    builtin = yaml.safe_load(_builtin_yaml().read_text(encoding="utf-8"))

    names = builtin.get("names") or {}
    if not names:
        raise RuntimeError("内置的 coco128.yaml 里没有类别表（names），无法生成数据集配置")

    lines = [
        "# 本文件由 src/yolo/dataset.py 生成，指向本地已下载的 coco128。",
        "# 不要手工修改，重新运行 `python src/main.py dataset` 会覆盖它。",
        f"path: {COCO128_DIR.as_posix()}",
        f"train: {builtin['train']}",
        f"val: {builtin['val']}",
        # 内置配置没有 nc 字段，类别数由 names 推导
        f"nc: {len(names)}",
        "names:",
    ]
    for index, name in names.items():
        lines.append(f"  {index}: {name}")

    COCO128_YAML.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"已生成数据集配置：{COCO128_YAML}")
