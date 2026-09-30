# aiu-interview

AIU 创智部二面项目（实战部分）。

目标：把**本地大模型**和**计算机视觉（YOLO）**串成一条完整的应用主线，而不是几个互不相干的 demo。

## 项目状态

| 阶段 | 内容 | 状态 |
| --- | --- | --- |
| Part 1 | 本地大模型部署（Ollama） | ✅ 已完成 |
| Part 1 | 智能体 / 后端服务 | ⬜ 未开始 |
| Part 1 | 应用形态：CLI | ⬜ 未开始 |
| Part 1 | 应用形态：Web | ⬜ 未开始 |
| Part 2 | YOLO 训练跑通 | ⬜ 未开始 |
| Part 2 | YOLO 实时推理部署 | ⬜ 未开始 |
| Part 2 | YOLO 接入应用 | ⬜ 未开始 |
| Part 3 | 硬件结合（进阶） | ⬜ 未开始 |
| Part 4 | Harness 搭建（进阶） | ⬜ 未开始 |
| Part 5 | 创意作品整合 | ⬜ 未开始 |

进度细节见 [`docs/journal.md`](docs/journal.md)（工程日志，记录每天的进展、卡点与思路）。

## 目录结构

```
aiu-interview/
├── README.md          项目总说明（本文件）
├── docs/
│   └── journal.md     工程日志：进展、卡点、解决方式、下一步
├── part1-llm/         本地大模型部署与智能体应用
└── part2-yolo/        YOLO 训练与实时推理部署
```

没有图片、权重、数据集散落在仓库里：大文件一律通过 `.gitignore` 拦截，可复现的下载/生成方式写在各子目录的 README 中。

## 运行环境

| 项 | 实际配置 |
| --- | --- |
| 操作系统 | Windows |
| GPU | NVIDIA GeForce RTX 5060 Laptop **8GB**（Blackwell 架构，算力 sm_120） |
| CPU / 内存 | Intel Core Ultra 7 251HX / 31.4 GB |
| Python | Miniconda 环境 `ai_project`（Python 3.10.21），位于 `D:\software\Miniconda3\envs\ai_project` |
| 大模型运行时 | Ollama 0.34.4（`http://127.0.0.1:11434`） |

### 从零复现环境

```powershell
# 1. 创建 Python 环境
#    若 PowerShell 中提示找不到 conda 命令，先执行一次 `conda init powershell` 并重开终端
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

YOLO 部分的依赖（PyTorch / ultralytics）安装方式见 [`part2-yolo/README.md`](part2-yolo/README.md)。

## 踩坑记录（对复现很关键）

- **RTX 50 系显卡必须装对 PyTorch 版本**。它是 Blackwell 架构（sm_120），需要 CUDA 12.8 及以上的 wheel；装错版本的典型症状是 `torch.cuda.is_available()` 返回 `True`，但一执行计算就报 `no kernel image is available for execution on the device`。
- **不要使用系统自带的 Python 3.14**。PyTorch 尚不支持该版本，所有命令一律在 `ai_project` 环境中执行。
- **不要提交大文件**。模型权重（`*.pt`）、数据集（`datasets/`）、训练产物（`runs/`）已在 `.gitignore` 中排除，复现所需的数据请按子目录 README 的说明获取。

## AI 使用说明

本项目在开发过程中使用了 AI 辅助（Claude Code / Reasonix 等），主要用于：环境排查、文档整理、代码骨架搭建。

所有 AI 生成的内容均经过人工验证后才提交；关键决策、卡点与解决过程如实记录在 [`docs/journal.md`](docs/journal.md)。

## 许可

[MIT](LICENSE)
