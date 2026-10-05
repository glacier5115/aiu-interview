"""Web 形态的服务端。

    app         FastAPI 应用装配（挂路由、挂静态页面）
    routes      HTTP 接口定义（含 SSE 流式推送）
    sessions    会话仓库：按 session_id 存放对话上下文
    static      前端静态页面

分层约定：本包只负责「算」和「推」，不做任何页面渲染判断；
页面渲染全部由 ``static/index.html`` 订阅事件流后自行完成。
"""
