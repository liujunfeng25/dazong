"""MobileNetV2 迁移学习训练脚本（移植自 ai-agent/aiagent/backend/train/train.py）。

子进程方式由 train_runner 调用：
    python -m services.recognition.train --data_dir ... --output ... --epochs ... --batch_size ... --status_file ...

类别目录名约定为 cat_{category_id}，class_mapping idx→"cat_{category_id}" 由本脚本写出。
"""
from __future__ import annotations

import argparse
import json
import random
import time
from collections import defaultdict
from pathlib import Path

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset
from torchvision import datasets, models, transforms


train_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.RandomCrop(224),
    transforms.RandomHorizontalFlip(),
    transforms.ColorJitter(brightness=0.2, contrast=0.2, saturation=0.2),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

# 验证集用确定性预处理（缩放+居中裁剪+归一化），与推理 inference.py 完全一致；
# 不做随机增强，验证准确率才反映真实表现。
val_transform = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])


def main() -> None:
    parser = argparse.ArgumentParser(description="智能秤识别 MobileNetV2 微调")
    parser.add_argument("--data_dir", type=str, required=True)
    parser.add_argument("--output", type=str, required=True)
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--status_file", type=str, default="")
    args = parser.parse_args()

    start_time: list[float | None] = [None]

    def write_status(
        status: str,
        epoch: int = 0,
        total_epochs: int = 0,
        loss: float = 0.0,
        train_acc: float = 0.0,
        val_acc: float = 0.0,
        message: str = "",
        batch_idx: int = 0,
        num_batches: int = 0,
    ) -> None:
        if not args.status_file:
            return
        if status == "running" and start_time[0] is None:
            start_time[0] = time.time()
        p = Path(args.status_file)
        p.parent.mkdir(parents=True, exist_ok=True)
        try:
            obj: dict = {
                "status": status,
                "epoch": epoch,
                "total_epochs": total_epochs,
                "loss": round(loss, 4),
                "train_acc": round(train_acc, 4),
                "val_acc": round(val_acc, 4),
                "message": message,
            }
            if batch_idx and num_batches > 0:
                obj["batch_idx"] = batch_idx
                obj["num_batches"] = num_batches
            if start_time[0]:
                obj["started_at"] = start_time[0]
            p.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        except Exception:
            pass

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"数据目录不存在: {data_dir}")

    class_names = sorted([d.name for d in data_dir.iterdir() if d.is_dir()])
    num_classes = len(class_names)
    if num_classes < 2:
        raise ValueError(f"至少需要 2 个类别，当前只有 {num_classes} 个")

    # 同一批文件建两个 ImageFolder：train 套增强、val 套干净预处理；
    # 二者文件顺序一致（ImageFolder 确定性排序），可用同一组下标分别取子集。
    train_base = datasets.ImageFolder(str(data_dir), transform=train_transform)
    val_base = datasets.ImageFolder(str(data_dir), transform=val_transform)
    if len(train_base) < 4:
        raise ValueError(f"样本总数过少（{len(train_base)} 张），无法训练")

    # 分层划分：按类各自抽 ~15% 作验证，且保证每类至少 1 张留在训练集；
    # 某类样本太少（<4 张）则整类进训练、不抽验证 —— 避免"整类被切去验证、训练没见过"。
    by_class: dict[int, list[int]] = defaultdict(list)
    for idx, (_, label) in enumerate(train_base.samples):
        by_class[label].append(idx)
    rng = random.Random(42)
    train_idx: list[int] = []
    val_idx: list[int] = []
    for label, idxs in by_class.items():
        idxs = idxs[:]
        rng.shuffle(idxs)
        n = len(idxs)
        n_val = 0 if n < 4 else max(1, min(int(n * 0.15), n - 1))
        val_idx += idxs[:n_val]
        train_idx += idxs[n_val:]

    train_dataset = Subset(train_base, train_idx)
    val_dataset = Subset(val_base, val_idx)
    has_val = len(val_idx) > 0
    train_loader = DataLoader(train_dataset, batch_size=args.batch_size, shuffle=True, num_workers=0)
    val_loader = DataLoader(val_dataset, batch_size=args.batch_size, shuffle=False, num_workers=0)

    weights = models.MobileNet_V2_Weights.IMAGENET1K_V1
    model = models.mobilenet_v2(weights=weights)
    model.classifier[1] = nn.Linear(model.last_channel, num_classes)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = model.to(device)
    # 冻结特征提取，只 fine-tune 分类头（与 ai-agent 一致）
    for param in model.features.parameters():
        param.requires_grad = False
    optimizer = torch.optim.Adam(model.classifier.parameters(), lr=args.lr)
    criterion = nn.CrossEntropyLoss()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    num_batches = len(train_loader)
    best_acc = 0.0
    idx_to_class = {str(i): name for i, name in enumerate(class_names)}

    write_status("running", epoch=0, total_epochs=args.epochs, message="训练开始…")
    for epoch in range(args.epochs):
        model.train()
        total_loss, correct, total = 0.0, 0, 0
        for batch_idx, (images, labels) in enumerate(train_loader):
            images, labels = images.to(device), labels.to(device)
            optimizer.zero_grad()
            outputs = model(images)
            loss = criterion(outputs, labels)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
            correct += (outputs.argmax(1) == labels).sum().item()
            total += labels.size(0)
            if (batch_idx + 1) % 5 == 0 or batch_idx == num_batches - 1:
                run_loss = total_loss / (batch_idx + 1)
                run_acc = correct / max(total, 1)
                write_status(
                    "running",
                    epoch=epoch + 1,
                    total_epochs=args.epochs,
                    loss=run_loss,
                    train_acc=run_acc,
                    batch_idx=batch_idx + 1,
                    num_batches=num_batches,
                )
        train_acc = correct / max(total, 1)
        model.eval()
        val_correct, val_total = 0, 0
        with torch.no_grad():
            for images, labels in val_loader:
                images, labels = images.to(device), labels.to(device)
                outputs = model(images)
                val_correct += (outputs.argmax(1) == labels).sum().item()
                val_total += labels.size(0)
        # 有验证样本→用干净图的验证准确率；无验证样本（各类都太少）→退回用训练准确率展示与选优
        if val_total > 0:
            val_acc = val_correct / val_total
            sel_acc = val_acc
        else:
            val_acc = train_acc
            sel_acc = train_acc
        epoch_loss = total_loss / max(len(train_loader), 1)
        write_status(
            "running",
            epoch=epoch + 1,
            total_epochs=args.epochs,
            loss=epoch_loss,
            train_acc=train_acc,
            val_acc=val_acc,
            message=f"Epoch {epoch + 1}/{args.epochs}",
            batch_idx=num_batches,
            num_batches=num_batches,
        )
        if sel_acc >= best_acc:
            best_acc = sel_acc
            torch.save(model, output_path)

    mapping_path = output_path.parent / "class_mapping.json"
    mapping_path.write_text(json.dumps(idx_to_class, ensure_ascii=False, indent=2), encoding="utf-8")
    _acc_label = "验证" if has_val else "训练"
    write_status(
        "done",
        epoch=args.epochs,
        total_epochs=args.epochs,
        val_acc=best_acc,
        message=f"训练完成，最佳{_acc_label}准确率: {best_acc:.1%}",
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001
        import sys

        status_file = ""
        for i, a in enumerate(sys.argv):
            if a == "--status_file" and i + 1 < len(sys.argv):
                status_file = sys.argv[i + 1]
                break
        if status_file:
            Path(status_file).parent.mkdir(parents=True, exist_ok=True)
            Path(status_file).write_text(
                json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False),
                encoding="utf-8",
            )
        raise
