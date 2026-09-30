# 工程日志

## 2026-09-30

### 今日完成
- 安装 Miniconda，创建 ai_project 环境（Python3）
- 安装 Git，配置用户名和邮箱
- 在 GitHub 创建 aiu-interview 仓库，克隆到文件夹
- 下载ollama并下载本地模型

### 卡点
- 找不到 Miniconda Prompt

### 解决
- 发现找错文件，搜索正确关键词找到文件

### 下一步
- 写 README 项目说明

## 2026-09-30（第二轮：补齐仓库地基）

### 今日完成
- 新建 `part1-llm/`、`part2-yolo/` 两个子目录，各写一份 README，说明该部分的目标、方案与计划清单
- 重写根 `README.md`：补上项目状态表、目录结构、硬件与软件环境、从零复现环境的命令、踩坑记录
- 修正一处文档与现实不符的问题：上一版 README 已经声明了 `part1-llm/`、`part2-yolo/` 目录，但当时目录其实并不存在，属于自相矛盾，已补齐
- `.gitignore` 补充大文件拦截规则（`*.pt`、`datasets/`、`runs/` 等），避免后续误提交权重和数据集
- 拉取 `qwen3:8b` 作为应用主模型

### 卡点
- PowerShell 里直接敲 `conda` 提示找不到命令，只能靠完整路径 `D:\software\Miniconda3\envs\ai_project\python.exe` 调用

### 解决
- 查明原因是 Miniconda 安装时没有写入 PATH。解决办法是执行一次 `conda init powershell` 后重开终端，即可正常使用 `conda activate`。目前已把这一点写进 README 的复现步骤，避免换台机器再踩

### 目前的想法
- 三个部分（LLM、YOLO、硬件）如果各自做一个孤立 demo，说明思路时会很散。打算先用 Part 1 + Part 2 串成一个应用（本地模型对话 + 视觉检测），再考虑进阶项，做减法而不是堆砌
- 8GB 显存是硬约束，模型和训练参数都要围绕这一点来选

### 下一步
- 写 Part 1 的 CLI 程序，打通"应用 → Ollama"的端到端链路

## 2026-09-30（第三轮：模型拉取与接口实测）

### 今日完成
- 成功拉取并验证 `qwen3:8b`（5.2 GB），作为应用主模型
- 实测并记录了 Ollama 两种 API 接口的差异、Qwen3 思考模式的关闭方式、8B 模型在本机的生成速度

### 卡点
- `ollama pull` 的进度条长时间停在 5.2GB 的最后一个百分比不动，我判断成"下载卡死"，杀掉了进程重新拉，前后折腾了三轮

### 解决
- 事后看服务端日志和 blobs 目录才发现，它其实一直在正常下载和校验，只是进度条不刷新。**教训：判断下载是否真的卡住，要看 `~/.ollama/models/blobs` 里 partial 文件的体积变化和 `server.log`，而不是信进度条**。已把这条排查方法写进 `part1-llm/README.md`
- 顺带实测了三个下载源的速度：ModelScope 约 7.2 MB/s，registry.ollama.ai 在 0.9~8 MB/s 之间剧烈波动，hf-mirror 只有约 0.13 MB/s。结论是以后拉大模型优先走魔搭

### 目前的想法
- 踩到一个会直接影响应用写法的坑：Qwen3 是思考模型，不关思考的话 `content` 会是空字符串，正文全被思考吃掉了。实测下来，Ollama 原生接口要用 `think: false`，OpenAI 兼容接口要用 `reasoning_effort: "none"`，而 prompt 里加 `/no_think` 在当前版本的 Ollama 模板下是无效的。这些结论已经记进笔记，避免后面写应用时再踩一遍
- 主模型定为 `qwen3:8b`，实测生成速度约 19 tok/s，交互体验够用

### 下一步
- 写 Part 1 的 CLI 程序，打通"应用 → Ollama"的端到端链路
- 之后再补 Web 形态