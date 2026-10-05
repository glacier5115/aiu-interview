# aiu-interview

AIU 创智部二面项目（实战部分）。

目标：把**本地大模型**和**计算机视觉（YOLO）**串成一条完整的应用主线，而不是几个互不相干的 demo。

## 项目状态

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Part 1 | 本地大模型部署（Ollama） | ✅ 已完成 |
| Part 1 | 应用形态一：CLI | ✅ 已完成 |
| Part 2 | Web 服务（后端 + 前端页面） | ✅ 已完成 |
| Part 3 | YOLO 训练跑通 | ✅ 已完成 |
| Part 3 | YOLO 实时推理部署 | ✅ 已完成 |
| Part 3 | YOLO 接入 Web 应用 | ⬜ 未开始 |
| 进阶 | 硬件结合（AI 控制单片机） | ⬜ 未开始 |
| 进阶 | Harness 搭建 | ⬜ 未开始 |
| 收尾 | 创意作品整合 | ⬜ 未开始 |

进度细节见 [`docs/journal.md`](docs/journal.md)（工程日志，记录每天的进展、卡点与思路）。

## 快速开始

前置条件：Ollama 正在运行，且已拉取 `qwen3:8b`（拉取方式见下方「从零复现环境」）。

```powershell
conda activate ai_project        # 必须用项目的 conda 环境，别用系统自带的 Python 3.14
pip install -r part1-llm/requirements.txt
pip install -r part2-web/requirements.txt
```

**形态一：命令行对话**

```powershell
cd part1-llm
python src/main.py
```

**形态二：Web 对话**（启动后浏览器打开 <http://127.0.0.1:8000>）

```powershell
cd part2-web
python src/main.py
```

**Part 3：YOLO 训练与推理**

```powershell
cd part3-yolo

# torch 必须从 PyTorch 官方源装 CUDA 版本，装成 CPU 版会报 no kernel image，
# 详细说明见 part3-yolo/README.md
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt

python src/main.py check                    # 确认 GPU 可用（算力应识别为 sm_120）
python src/main.py dataset                  # 准备 coco128（约 7MB）
python src/main.py train                    # 训练，约 2 分钟
python src/main.py predict --source 图片.jpg
```

如果报 `ModuleNotFoundError`，说明用错了 Python 解释器：先执行一次 `conda init powershell`
（cmd 用 `conda init cmd.exe`）并重开终端，或者直接用
`D:\software\Miniconda3\envs\ai_project\python.exe` 来运行。

## 目录结构

```
aiu-interview/
├── README.md              项目总说明（本文件）
├── shared/                跨应用形态复用的核心代码
│   └── llm_chat/          与 Ollama 通信、维护会话上下文（Part 1 和 Part 2 共用）
├── part1-llm/             应用形态一：命令行对话
│   ├── README.md
│   ├── requirements.txt
│   └── src/
│       ├── main.py        程序入口
│       └── cli/           CLI 展示层（terminal / repl）
├── part2-web/             应用形态二：Web 服务（后端 + 前端页面）
│   ├── README.md
│   ├── requirements.txt
│   └── src/
│       ├── main.py        程序入口
│       └── server/        FastAPI 应用、接口、会话仓库、前端页面
├── part3-yolo/            YOLO 训练与实时推理
│   ├── README.md
│   ├── requirements.txt
│   └── src/
│       ├── main.py        入口（check / dataset / train / predict）
│       └── yolo/          config / assets / dataset / train / predict
└── docs/
    └── journal.md         工程日志：进展、卡点、解决方式、下一步
```

`shared/` 里只放与界面无关的逻辑，各个 part 只放自己的展示层——所以 Part 1 和
Part 2 共享同一份「调用模型」的代码，而不是各写一遍。

没有图片、权重、数据集散落在仓库里：大文件一律通过 `.gitignore` 拦截，可复现的
下载/生成方式写在各子目录的 README 中。

## 运行环境

| 项 | 实际配置 |
| --- | --- |
| 操作系统 | Windows |
| GPU | NVIDIA GeForce RTX 5060 Laptop **8GB**（Blackwell 架构，算力 sm_120） |
| CPU / 内存 | Intel Core Ultra 7 251HX / 31.4 GB |
| Python | Miniconda 环境 `ai_project`（Python 3.10.21），位于 `D:\software\Miniconda3\envs\ai_project` |
| 大模型运行时 | Ollama 0.34.4（`http://127.0.0.1:11434`） |
| 视觉推理 | PyTorch 2.11.0+cu128 / ultralytics 8.4.173 |

### 从零复现环境

```powershell
# 1. 创建 Python 环境
#    若提示找不到 conda 命令，先执行一次 conda init（PowerShell 用 conda init powershell，
#    cmd 用 conda init cmd.exe）并重开终端
conda create -n ai_project python=3.10 -y
conda activate ai_project

# 2. 安装 Ollama（Windows 安装包），确认服务可用
ollama --version

# 3. 拉取本项目的模型
ollama pull qwen3:8b            # 对话主模型，约 5GB
ollama pull qwen2.5-coder:1.5b  # 轻量模型，用于快速验证链路

# 4. 验证
ollama list
```

YOLO 部分的依赖（PyTorch / ultralytics）安装方式见 [`part3-yolo/README.md`](part3-yolo/README.md)。

## 踩坑记录（对复现很关键）

- **必须用项目的 conda 环境**。直接敲 `python` 很可能落到系统自带的 Python 3.14 上，
  那个环境没有装依赖，会报 `ModuleNotFoundError`。所有命令都要先 `conda activate ai_project`。
- **RTX 50 系显卡必须装对 PyTorch 版本**。它是 Blackwell 架构（sm_120），需要 CUDA 12.8 及以上的 wheel；装错版本的典型症状是 `torch.cuda.is_available()` 返回 `True`，但一执行计算就报 `no kernel image is available for execution on the device`。
- **不要提交大文件**。模型权重（`*.pt`）、数据集（`datasets/`）、训练产物（`runs/`）已在 `.gitignore` 中排除，复现所需的数据请按子目录 README 的说明获取。

## AI 使用说明

本项目在开发过程中使用了 AI 辅助（Claude Code / Reasonix 等），主要用于：环境排查、文档整理、代码骨架搭建。

所有 AI 生成的内容均经过人工验证后才提交；关键决策、卡点与解决过程如实记录在 [`docs/journal.md`](docs/journal.md)。

## 许可

[MIT](LICENSE)
