# Part 1 — 本地大模型与智能体应用

状态：**CLI 已完成，Web 形态待开发**

## 目标

1. 在本机部署本地大模型（已通过 Ollama 完成）
2. 让本地模型充当 model provider，以 API 形式接入自己写的应用
3. 应用形态由易到难推进：CLI → Web

## 方案

Ollama 直接对外提供两种接口，应用侧按需选一种即可，不需要自研通信协议：

| 接口 | 地址 | 特点 |
| --- | --- | --- |
| Ollama 原生 | `http://127.0.0.1:11434/api/chat` | 功能最全，支持 `think` 等原生参数 |
| OpenAI 兼容 | `http://127.0.0.1:11434/v1/chat/completions` | 可以直接复用 `openai` SDK，便于后续换云端模型 |

## 本机模型清单（实测）

| 模型 | 大小 | 用途 |
| --- | --- | --- |
| `qwen3:8b` | 5.2 GB | **应用主模型**，可完整放进 8GB 显存 |
| `qwen2.5-coder:1.5b` | 0.9 GB | 轻量模型，用于快速验证链路 |
| `nomic-embed-text` | 0.3 GB | 文本向量化（为后续 RAG 预留） |
| `qwen3.6-nocensor` | 22.3 GB | 36B MoE，显存放不下、需大量 CPU 卸载，仅作能力展示，不作主模型 |

## 实测笔记（踩过的坑）

### 1. Qwen3 是思考模型，不关思考会拿不到正文

Qwen3 默认先输出一段"思考"文本，会直接吃满 token 配额，导致 `content` 返回空字符串。实测四种写法的有效性：

| 写法 | 结果 |
| --- | --- |
| `/api/chat` + `"think": false` | ✅ 正常返回正文 |
| `/v1/chat/completions` + `"reasoning_effort": "none"` | ✅ 正常返回正文 |
| `/v1/chat/completions` + `"think": false` | ❌ 无效，思考照旧占满输出 |
| prompt 里加 `/no_think`（放在 user 或 system 均试过） | ❌ 无效 |

**结论**：用 OpenAI SDK 接入时，记得显式传 `reasoning_effort="none"`；或者改用 Ollama 原生接口。

### 2. 生成速度

`qwen3:8b`（关闭思考）在 RTX 5060 Laptop 8GB 上实测约 **19 tok/s**，模型完整加载在显存中，属于可正常交互的水平。

### 3. `ollama pull` 的进度条会"假装卡死"

拉取 `qwen3:8b` 时，进度条长时间停在同一个数值（5.2GB 的最后一个百分比）不动，看起来像断流了，实际上是仍在后台下载和校验。**中途不要急着重启或杀进程**，已下载的部分是能续传的。

判断是否真的卡住，看这两个地方比看进度条可靠：

```powershell
# 1. blobs 目录里 -partial 文件的大小是否在增长
Get-ChildItem "$env:USERPROFILE\.ollama\models\blobs" -File -Filter "*partial*" |
  Sort-Object Length -Descending | Select-Object -First 1 Name, Length

# 2. 服务端日志
Get-Content "$env:LOCALAPPDATA\Ollama\server.log" -Tail 20
```

### 4. 拉取源速度差异很大（本机实测）

| 源 | 实测速度 |
| --- | --- |
| ModelScope 魔搭 | ~7.2 MB/s |
| registry.ollama.ai | 0.9 ~ 8 MB/s（波动很大） |
| hf-mirror.com | ~0.13 MB/s |

如果 `ollama pull` 实在太慢，可以改用 ModelScope 下载 GGUF 权重，再 `ollama create` 导入。

## 运行 CLI

> **必须先激活项目的 conda 环境。** 直接敲 `python` 很可能落到系统自带的
> Python 3.14 上，那个环境没有安装依赖，会报
> `ModuleNotFoundError: No module named 'requests'`。
> 若提示找不到 `conda` 命令，先执行一次 `conda init powershell`（cmd 用
> `conda init cmd.exe`）并重开终端。

```powershell
conda activate ai_project
cd part1-llm
pip install -r requirements.txt
python src/main.py
```

不方便配置 conda 时，也可以直接指定该环境的解释器：

```powershell
D:\software\Miniconda3\envs\ai_project\python.exe src\main.py
```

启动后会看到提示符，直接输入问题即可，回复是逐字流式输出的：

```
已连接 http://127.0.0.1:11434，当前模型 qwen3:8b
输入 /help 查看命令，/exit 退出

你 > 用一句话介绍你自己
qwen3:8b > 我是一个乐于助人的中文助手，致力于提供简洁、准确的信息和帮助。
```

对话中可用的命令：

| 命令 | 作用 |
| --- | --- |
| `/help` | 显示帮助 |
| `/clear` | 清空对话上下文（保留 system prompt） |
| `/model [名称]` | 切换模型；不带名称时列出本机所有模型 |
| `/exit` | 退出（`/quit`、`/q` 同效） |

常用参数：

```powershell
python src/main.py --model qwen2.5-coder:1.5b   # 换用轻量模型，响应更快
python src/main.py --think                      # 打开思考模式，观察模型的完整思考过程
python src/main.py --system ""                  # 禁用 system prompt
python src/main.py --help                       # 查看全部参数
```

## 目录结构

```
part1-llm/
├── README.md
├── requirements.txt        仅依赖 requests，其余全部使用 Python 标准库
└── src/
    ├── main.py             程序入口：只做参数解析与模块组装，不含业务逻辑
    └── cli/
        ├── terminal.py     终端显示工具（转义序列过滤等）
        └── repl.py         CLI 交互循环
```

Part 1 是「CLI 展示层 + 共享核心」的组合：

- **CLI 专属**的部分都在 `src/cli/`。这一层只处理终端交互，换一种应用形态时
  整体替换即可——Part 2 的 Web 版就是这么做的
- **与界面无关**的核心逻辑（与 Ollama 通信、维护会话上下文、默认配置）位于仓库
  顶层的 `shared/llm_chat/` 包里，被 Part 1 和 Part 2 共用，同一份逻辑不写两遍

`main.py` 启动时会把仓库根目录加入导入路径，所以从哪个目录运行都能找到 `shared` 包。

`client.chat_stream()` 产出的是模型原文，不做渲染处理——终端转义序列的过滤放在
`cli/terminal.py` 里，由展示层在渲染时调用。"取数据"和"怎么显示"是分开的，
换输出目标时核心代码不需要改动。

## 计划

- [x] CLI 对话程序
- [x] Web 服务（见 [`part2-web/`](../part2-web)）
- [ ] 接入 Part 3 的 YOLO 推理结果
