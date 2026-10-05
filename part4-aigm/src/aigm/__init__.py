"""AI GM 跑团的核心。

    config      默认参数
    rules       骰子与检定规则（纯逻辑，不依赖模型与网络）
    character   角色卡
    gamestate   一局的状态与存档
    prompts     GM 的提示词
    gm          GM 引擎：把玩家的行动推进成一个回合

这一层不依赖任何 Web 框架，命令行或测试脚本都能直接用。Web 层在上一级的
server 包里。
"""
