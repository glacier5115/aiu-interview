"""终端显示相关的小工具。

属于 CLI 展示层：只处理「怎么显示」，不产生数据。
"""

from __future__ import annotations

import re

# 模型输出的文本会被直接打到终端上。如果其中带 ANSI 转义序列
# （例如被诱导复述了一段含 ESC 的内容），就可能操纵终端显示效果，
# 因此显示前统一过滤掉，只保留换行和制表符。
_TERMINAL_ESCAPE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"               # CSI 序列
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)"    # OSC 序列
    r"|\x1b[@-Z\\-_]"                        # 其他两字节转义
    r"|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"    # 控制字符（保留 \t \n \r）
)


def sanitize(text: str) -> str:
    """过滤掉可能操纵终端显示的转义序列。

    只作用于显示，存进对话上下文的仍然会是模型返回的原文。
    """
    return _TERMINAL_ESCAPE.sub("", text)
