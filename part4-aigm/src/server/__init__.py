"""Web 形态的服务端。

    app        FastAPI 应用装配
    routes     HTTP 接口
    games      进行中的对局
    static     前端页面

核心逻辑在上一级的 ``aigm`` 包里（规则、角色、GM 引擎），这一层只负责把它
接到 HTTP 上，不做任何规则判断。
"""
