"""CLI 形态的展示层。

    terminal   终端显示工具（转义序列过滤等）
    repl       交互式对话主循环

这一层是 part1-llm 专属的。核心逻辑在顶层的 ``shared.llm_chat`` 包里，
换一种应用形态（例如 part2-web）时替换掉本包即可。
"""
