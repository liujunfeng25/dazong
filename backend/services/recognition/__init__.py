"""智能秤识别真训练子系统：移植自 ai-agent 的 MobileNetV2 迁移学习流水线。

- train.py: 训练脚本（subprocess 入口）
- train_runner.py: 启动/查状态/取消子进程
- inference.py: 加载模型 + 推理（LRU 缓存）
- materialize.py: 把 Sample 图从 MinIO 下载到本地 ImageFolder 目录

运行产物落在 backend/data/smart_scale_recognition/ 下，靠 ./backend:/app 卷持久化。
"""
