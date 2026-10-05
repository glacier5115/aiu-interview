# Part 2 — 本地大模型的 Web 服务

状态：**已完成（对话功能）**

## 目标

把 Part 1 的对话能力搬到浏览器里，做成前后端分离的 Web 服务：
后端只负责调用模型和推送结果，前端只负责界面和订阅。

## 前后端如何解耦

约定只有一条：**后端推送结构化事件，前端自己决定怎么显示**。

| | 负责 | 不负责 |
| --- | --- | --- |
| 后端 | 调用模型、维护会话上下文、把结果拆成事件推送 | 不生成任何 HTML 片段，不判断该怎么渲染 |
| 前端 | 渲染消息、更新状态、收集输入、订阅事件流 | 不拼 prompt、不维护对话历史、不判断模型状态 |

两者之间只有 HTTP + SSE 一种联系方式。前端是一份纯静态文件，后端是一个
FastAPI 应用，替换任何一边都不用动另一边。

## 接口

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| `GET` | `/api/health` | 服务状态：是否连得上 Ollama、当前模型、已有会话数 |
| `POST` | `/api/chat` | 发起一轮对话，以 SSE 流式返回结果 |
| `POST` | `/api/session/reset` | 清空指定会话的上下文 |
| `GET` | `/` | 前端页面 |

`/api/chat` 推送的事件格式（SSE 的 `data:` 报文，一行一个 JSON）：

```
data: {"type": "delta", "content": "你"}      增量文本，前端追加到当前气泡
data: {"type": "error", "message": "..."}     出错信息
data: {"type": "done"}                        本轮结束
```

会话由前端生成 `session_id` 存在浏览器 `localStorage` 里，后端据此找回上下文，
所以多个标签页之间互不干扰。

## 运行

> 必须先激活 conda 环境（与 Part 1 相同，直接敲 `python` 会落到系统解释器上）。

```powershell
conda activate ai_project
cd part2-web
pip install -r requirements.txt
python src/main.py
```

然后浏览器打开 <http://127.0.0.1:8000> 。

常用参数：

```powershell
python src/main.py --port 8080                  # 换端口
python src/main.py --model qwen2.5-coder:1.5b   # 换模型，响应更快
python src/main.py --bind 0.0.0.0               # 让同网段设备也能访问，注意下面的提醒
```

**关于 `--bind 0.0.0.0`**：这会把服务暴露给同网段的所有设备，而本服务**没有鉴权**，
任何人都能借你的机器跑模型。只在自己清楚风险的临时场景下使用，用完及时关闭。
默认只监听 `127.0.0.1`，只有本机能访问。

## 目录结构

```
part2-web/
├── README.md
├── requirements.txt          fastapi / uvicorn / requests
└── src/
    ├── main.py               程序入口：只做参数解析与模块组装
    └── server/
        ├── app.py            FastAPI 应用装配（挂路由 + 挂静态页面）
        ├── routes.py         HTTP 接口与 SSE 推送
        ├── sessions.py       会话仓库（按 session_id 存放上下文）
        └── static/          前端（原生 HTML/CSS/JS，无需构建工具）
            ├── index.html   页面结构
            ├── style.css    样式：浅色 / 深色两套配色
            ├── markdown.js  极简 Markdown 渲染器
            └── app.js       交互逻辑与事件流订阅
```

核心逻辑来自顶层的 `shared/llm_chat`（与 Part 1 共用同一份代码，不重复实现）。
前端页面由同一个服务提供，因此前后端同源，不需要配置 CORS。

## 前端

- **双主题**：浅色 / 深色两套配色，默认跟随系统；右上角按钮在「跟随系统 → 浅色 → 深色」
  之间循环切换，选择记在浏览器 `localStorage` 里
- **Markdown 渲染**：回复里的代码块、列表、粗体等渲染成正常排版，代码块带语言标记和一键复制
- **不依赖任何第三方库**：没有 npm、没有打包步骤，也没有 CDN 引用——断网也能正常显示

`markdown.js` 是自己写的轻量渲染器，关键点是**先转义 HTML 再套格式**：模型输出属于
不可信内容，如果直接当成 HTML 插入页面，模型返回的 `<script>` 会被浏览器真的执行。

## 后续

- [ ] 接入 Part 3 的 YOLO 检测结果（后端加一条检测接口，前端加一个图片上传入口）
