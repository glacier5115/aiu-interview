# Part 2 — 本地大模型的 Web 服务

状态：**已完成（对话 + 视觉检测）**

## 目标

把 Part 1 的对话能力和 Part 3 的视觉检测都搬到浏览器里，做成前后端分离的
Web 服务：后端只负责计算和推送，前端只负责界面和订阅。

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
| `GET` | `/api/health` | 服务状态：是否连得上 Ollama、当前模型、会话数、检测模型是否就绪 |
| `POST` | `/api/chat` | 发起一轮对话，以 SSE 流式返回结果 |
| `POST` | `/api/detect` | 上传一张图片做目标检测，返回结构化的检测框 |
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

`/api/detect` 返回的同样是**数据**，不是画好的图片：

```json
{"ok": true, "width": 640, "height": 480, "elapsed_ms": 11.3,
 "detections": [{"label": "zebra", "confidence": 0.96, "box": [0, 19, 442, 405]}]}
```

前端拿到框的坐标后自己叠在图片上——颜色、标签样式、悬停效果都由前端决定，
所以想改成画在 canvas 上或者列成表格，都不用动后端。

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
            ├── index.html   页面结构（两个面板：对话 / 视觉检测）
            ├── style.css    样式：浅色 / 深色两套配色
            ├── markdown.js  极简 Markdown 渲染器
            ├── app.js       对话逻辑、面板切换、事件流订阅
            └── vision.js    检测页：上传、调用接口、把检测框画到图片上
```

核心逻辑来自顶层 `shared/` 下的两个包，都不是为本服务单独写的：

- `shared/llm_chat` —— 与 Ollama 通信、维护会话上下文（与 Part 1 共用）
- `shared/vision` —— YOLO 检测器（与 Part 3 共用）

前端页面由同一个服务提供，因此前后端同源，不需要配置 CORS。

## 前端

- **双主题**：浅色 / 深色两套配色，默认跟随系统；右上角按钮在「跟随系统 → 浅色 → 深色」
  之间循环切换，选择记在浏览器 `localStorage` 里
- **Markdown 渲染**：回复里的代码块、列表、粗体等渲染成正常排版，代码块带语言标记和一键复制
- **两个面板**：顶栏可切换「对话」和「视觉检测」。切换只是显示/隐藏，DOM 和状态
  都留着，来回切不会把聊过的内容或检测结果弄丢
- **检测页**：拖拽或点击上传图片，检测框直接叠在图上（用百分比定位，图片缩放时框会
  跟着走），右侧列出每个目标的类别与置信度，标签颜色按类别分配
- **不依赖任何第三方库**：没有 npm、没有打包步骤，也没有 CDN 引用——断网也能正常显示

`markdown.js` 是自己写的轻量渲染器，关键点是**先转义 HTML 再套格式**：模型输出属于
不可信内容，如果直接当成 HTML 插入页面，模型返回的 `<script>` 会被浏览器真的执行。

## 显存说明

对话模型（qwen3:8b 约占 5.2GB）与检测模型同时驻留显存，在 8GB 的卡上比较紧凑。
只做对话时加 `--no-vision` 可以跳过检测模型；反过来，没装 ultralytics 也能正常跑
对话，只是检测接口会返回明确的错误提示，不会拖垮服务。
