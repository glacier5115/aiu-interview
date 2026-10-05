# Part 3 — YOLO 训练与实时推理

状态：**训练与推理已跑通**；与 Web 的集成待做

## 目标

1. 用 ultralytics 完成一次完整的 YOLO 训练
2. 完成实时推理部署（先用 Python 快速实现，再考虑用 C++/Rust 优化）
3. 把推理结果接入 Part 2 的 Web 服务

## 环境安装（关键：RTX 50 系是 sm_120）

本机 GPU 是 RTX 5060 Laptop，Blackwell 架构、算力 **sm_120**。装错 PyTorch 版本的
典型症状是 `torch.cuda.is_available()` 返回 `True`，但一执行计算就报
`no kernel image is available for execution on the device`。

```powershell
conda activate ai_project

# 第一步：先从 PyTorch 官方源装 CUDA 版本（走默认的 PyPI 会装成 CPU 版）
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# 第二步：再装 ultralytics（此时 torch 已满足要求，不会被替换掉）
pip install -r requirements.txt
```

装完先验证：

```powershell
cd part3-yolo
python src/main.py check
```

期望输出里包含：

```
CUDA 可用    True
设备        NVIDIA GeForce RTX 5060 Laptop GPU
算力        sm_120
```

## 使用

```powershell
python src/main.py check                       # 检查环境与 GPU
python src/main.py dataset                     # 下载并准备 coco128（约 7MB）
python src/main.py train                       # 训练
python src/main.py train --epochs 100 --batch 8
python src/main.py predict --source 图片.jpg
python src/main.py predict --source 0          # 摄像头
python src/main.py predict --source 视频.mp4 --conf 0.4
```

## 实测结果

### 训练

数据集 coco128（128 张图）+ 预训练权重 yolo11n，50 轮，batch 16，imgsz 640：

| 指标 | 值 |
| --- | --- |
| precision | 0.858 |
| recall | 0.764 |
| **mAP50** | **0.846** |
| mAP50-95 | 0.673 |
| 训练耗时 | 约 2 分钟 |

coco128 只有 128 张图，它的作用是验证流程跑得通，不适合用来证明模型能力。

### 推理性能

RTX 5060 Laptop 8GB，预热后连续跑 100 张图：

| 输入尺寸 | 单张耗时 | 吞吐 |
| --- | --- | --- |
| 640 | 6.6 ms | **152 FPS** |
| 480 | 4.5 ms | 224 FPS |
| 320 | 3.3 ms | 305 FPS |

模型加载 27 ms；**冷启动首帧 3.9 秒**（CUDA 初始化与底层算法选型的一次性开销），
之后进入上面的稳定帧率。摄像头实时场景通常要求 30 FPS，640 尺寸下有三倍以上余量。

## 目录结构

```
part3-yolo/
├── README.md
├── requirements.txt
├── src/
│   ├── main.py             入口：子命令分发（check / dataset / train / predict）
│   └── yolo/
│       ├── config.py       默认参数与路径
│       ├── assets.py       联网资源获取：体积校验 + 断点续传 + 多源重试
│       ├── dataset.py      数据集准备
│       ├── train.py        训练封装
│       └── predict.py      推理封装
├── datasets/               coco128 数据集（不入库）
├── weights/                预训练权重（不入库）
└── runs/                   训练与推理产物（不入库）
```

训练产物里值得展示的是 `results.png`（指标曲线）、`confusion_matrix.png`（混淆矩阵）
和 `val_batch0_pred.jpg`（验证集预测可视化）。它们都在 `runs/` 下，因为体积原因不提交，
需要时重新训练即可生成。

## 踩坑记录

- **内置配置里没有 `nc` 字段**：ultralytics 8.4 的 `coco128.yaml` 用 `names` 推导
  类别数，直接读 `builtin["nc"]` 会 KeyError。
- **下载中断，但 HTTP 状态码是 200**：本机到 GitHub 的连接不稳定，coco128 第一次
  下到一半被重置、yolo11n.pt 第一次只下到 72% 就停了，两次状态码都是 200。只看状态码
  会把半截文件当成成功，必须按文件体积校验并支持 Range 续传（见 `assets.py`）。

## 后续

- [ ] 接入 Part 2 的 Web 服务：后端加一条检测接口，前端加图片上传入口
