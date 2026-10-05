"""联网资源的获取：预训练权重、数据集压缩包。

本机到 GitHub 的连接不稳定，下载常在中途断掉，所以这里做了两件事：

    1. **按文件体积校验完整性**，不能只看 HTTP 状态码——传输中断时状态码同样是 200；
    2. **断点续传 + 多源重试**，网络抖动之后接着下，而不是从头再来一遍。

这两条都是实测踩出来的：coco128 第一次下到一半连接被重置，yolo11n.pt 第一次只
下到 72% 就停了，而两次的 HTTP 状态码都是 200。
"""

from __future__ import annotations

import urllib.error
import urllib.request
from pathlib import Path

from .config import (
    PRETRAINED_PATH,
    PRETRAINED_SIZE,
    PRETRAINED_SOURCES,
)

_CHUNK = 256 * 1024
_TIMEOUT = 30


def download(url: str, dest: Path, *, expected_size: int | None = None, retries: int = 4) -> None:
    """下载文件。

    expected_size 已知时用它判断是否下载完整；不完整就带着 Range 头续传重试。
    """
    dest.parent.mkdir(parents=True, exist_ok=True)

    for attempt in range(1, retries + 1):
        if _is_complete(dest, expected_size):
            return

        offset = dest.stat().st_size if dest.exists() else 0
        try:
            _fetch(url, dest, offset=offset)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            print(f"    第 {attempt} 次中断（已收到 {offset} 字节）：{exc}")

    if not _is_complete(dest, expected_size):
        size = dest.stat().st_size if dest.exists() else 0
        raise RuntimeError(f"重试 {retries} 次后仍不完整（{size} / {expected_size}）：{url}")


def _is_complete(dest: Path, expected_size: int | None) -> bool:
    """文件是否存在，以及（在已知体积时）大小是否吻合。"""
    if not dest.exists():
        return False
    if expected_size is None:
        return True
    return dest.stat().st_size == expected_size


def _fetch(url: str, dest: Path, *, offset: int) -> None:
    """执行一次下载。offset 大于 0 时请求续传。"""
    request = urllib.request.Request(url, headers={"User-Agent": "aiu-interview/1.0"})
    if offset:
        request.add_header("Range", f"bytes={offset}-")

    with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
        # 服务器不支持 Range 时会返回 200，此时必须从头写，否则文件会拼接错乱
        mode = "ab" if offset and response.status == 206 else "wb"
        with dest.open(mode) as handle:
            while True:
                chunk = response.read(_CHUNK)
                if not chunk:
                    break
                handle.write(chunk)


def ensure_pretrained_weights() -> Path:
    """确保预训练权重就绪，返回其路径。

    多个源依次尝试：GitHub 连不上时自动换到国内镜像。
    """
    if _is_complete(PRETRAINED_PATH, PRETRAINED_SIZE):
        print(f"预训练权重已就绪：{PRETRAINED_PATH.name}")
        return PRETRAINED_PATH

    megabytes = PRETRAINED_SIZE // 1024 // 1024
    print(f"正在获取预训练权重 {PRETRAINED_PATH.name}（约 {megabytes} MB）……")

    last_error: Exception | None = None
    for url in PRETRAINED_SOURCES:
        host = url.split("/")[2]
        try:
            download(url, PRETRAINED_PATH, expected_size=PRETRAINED_SIZE, retries=3)
            print(f"  已就绪（来源 {host}）：{PRETRAINED_PATH}")
            return PRETRAINED_PATH
        except Exception as exc:  # noqa: BLE001  换源比区分异常类型更重要
            last_error = exc
            print(f"  来源 {host} 不可用，换下一个")

    raise RuntimeError(f"所有下载源都失败了，最后一个错误：{last_error}")
