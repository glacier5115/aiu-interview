"""默认配置与常量。

所有默认值集中在这一处，避免散落到各个模块里难以查找和统一修改。
"""

from __future__ import annotations

DEFAULT_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:8b"
DEFAULT_SYSTEM_PROMPT = "你是一个乐于助人的中文助手，回答简洁、准确。"
DEFAULT_TEMPERATURE = 0.7

# 请求超时（连接秒数, 读取秒数）。读取时间放得比较宽，因为模型首次加载
# 进显存和生成较长回复都需要时间。
REQUEST_TIMEOUT = (5, 300)

# 探测服务是否在线的短超时
PROBE_TIMEOUT = 5
