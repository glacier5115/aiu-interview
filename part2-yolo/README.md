# Part 2 — YOLO 训练与实时推理

状态：**规划中**

## 目标

1. 用 ultralytics 完成一次完整的 YOLO 训练
2. 完成实时推理部署（先 Python 快速实现，再考虑用 C++/Rust 优化，优先复用成熟开源库而非自研）
3. 把推理结果接入应用（Web / 桌面端）

## 环境安装（GPU：RTX 5060 Laptop 8GB，sm_120）

```powershell
conda activate ai_project

# 1. 必须先单独安装 CUDA 12.8+ 版本的 PyTorch，
#    否则 ultralytics 会把 torch 装成不支持的默认版本，运行时报 sm_120 相关错误
pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

# 2. 再装 ultralytics
pip install ultralytics

# 3. 验证 GPU 可用（应输出 True 和 (12, 0)）
python -c "import torch; print(torch.cuda.is_available(), torch.cuda.get_device_capability())"
```

具体可用的 wheel 版本以 https://pytorch.org/get-started/locally/ 为准。

## 计划

- [ ] 准备数据集（先用 `coco128` 等小数据集跑通流程，控制显存占用）
- [ ] 完成一次训练并记录参数与指标
- [ ] 实时推理（摄像头 / 视频流）
- [ ] 接入应用

## 说明

训练产物（`runs/`、权重 `*.pt`）不会提交到仓库，最终结果以指标曲线和截图的形式保存在 `docs/` 下。
