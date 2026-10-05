"""从不完整的 JSON 流里提取字段值。

模型流式生成 JSON 时，我们拿到的是**半个 JSON 字符串**——没法直接 ``json.loads``，
但又想趁它还在写的时候就显示出来。所以需要能「边收边猜」：

    收到 ``{"narration": "你推开那扇``    → 提取出「你推开那扇」
    收到 ``{"narration": "你推开那扇门``  → 提取出「你推开那扇门」

做法是找到字段名后面那个字符串的起始引号，再逐字符读下去、处理转义，
遇到未转义的引号或文本末尾就停下。没读完的转义序列（例如刚收到一个反斜杠，
或者 ``\\uXXXX`` 只到一半）这一轮先丢掉——下一个 chunk 会把它补全。

这一层不理解 JSON 结构，只认「某个字段的字符串值」，因此也不怕模型在字段之间
插空白或换行。
"""

from __future__ import annotations

import re

_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    '"': '"',
    "\\": "\\",
    "/": "/",
    "b": "\b",
    "f": "\f",
}


def extract_string(buffer: str, field: str) -> str:
    """从可能不完整的 JSON 文本里，取出某个字符串字段当前的值。

    找不到该字段、或者值还没开始写，都返回空串。
    """
    match = re.search(r'"%s"\s*:\s*"' % re.escape(field), buffer)
    if not match:
        return ""

    rest = buffer[match.end():]
    out: list[str] = []
    index = 0

    while index < len(rest):
        char = rest[index]

        if char == "\\":
            if index + 1 >= len(rest):
                break  # 转义符刚收到，等下一个 chunk
            nxt = rest[index + 1]
            if nxt == "u":
                if index + 6 > len(rest):
                    break  # \uXXXX 没收全
                try:
                    out.append(chr(int(rest[index + 2 : index + 6], 16)))
                except ValueError:
                    break
                index += 6
                continue
            out.append(_ESCAPES.get(nxt, nxt))
            index += 2
            continue

        if char == '"':
            break  # 字符串结束

        out.append(char)
        index += 1

    return "".join(out)


class FieldDelta:
    """跟踪一个字段的增长，只产出新增的那部分。

    之所以要「跟踪」而不是每次都给全量：前端要做的是**追加**，
    给全量的话每来一个 chunk 都要重绘整段文字。
    """

    def __init__(self, field: str) -> None:
        self.field = field
        self._seen = ""

    @property
    def full(self) -> str:
        """到目前为止收到的完整值。"""
        return self._seen

    def feed(self, buffer: str) -> str:
        """喂进当前缓冲区，返回相比上次新增的部分（可能为空）。"""
        current = extract_string(buffer, self.field)

        # 值比上次短：多半是转义序列还没收全（例如刚读到一个反斜杠），
        # 这一轮先不动，等下一个 chunk 补齐
        if not current.startswith(self._seen):
            return ""

        delta = current[len(self._seen) :]
        self._seen = current
        return delta
