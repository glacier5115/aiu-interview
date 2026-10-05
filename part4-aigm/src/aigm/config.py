"""Part 4 的默认配置。

LLM 的连接参数（host / model）复用 shared/llm_chat 的默认值，这里只放
跑团特有的东西。
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAVES_DIR = PROJECT_ROOT / "saves"

# GM 的采样温度：叙事需要一点创造力
GM_TEMPERATURE = 0.8

# 结构化指令（判断要不要检定、生成状态变更）用低温度，保证输出稳定
STRUCTURED_TEMPERATURE = 0.3

# 构造提示词时保留多少轮原文对话，更早的内容进剧情摘要
RECENT_TURNS = 8

# 每推进多少轮刷新一次剧情摘要
SUMMARY_EVERY = 6
