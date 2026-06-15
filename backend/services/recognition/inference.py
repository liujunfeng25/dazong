"""服务端推理（移植自 ai-agent/app/services/inference.py）。

LRU 缓存 5 个 (model_path, mapping_path) 组合，避免每次 recognize 都重新加载 model.pt。
"""
from __future__ import annotations

import json
from pathlib import Path

import torch
from PIL import Image
from torchvision import transforms


_preprocess = transforms.Compose([
    transforms.Resize(256),
    transforms.CenterCrop(224),
    transforms.ToTensor(),
    transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
])

MAX_CACHE = 5
_cache: dict[tuple[str, str], dict] = {}


def _load_class_mapping(path: str | None) -> dict:
    if not path or not Path(path).exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        m = json.load(f)
    return {str(k): v for k, v in m.items()}


def load_model(model_path: str, class_mapping_path: str | None, device: str = "cpu"):
    """缓存命中即返回；未命中加载 model.pt 与 mapping，按加入顺序 LRU 淘汰。"""
    mapping_path = class_mapping_path or ""
    key = (model_path, mapping_path)
    if key in _cache:
        return _cache[key]["model"]

    if not Path(model_path).exists():
        raise FileNotFoundError(f"模型文件不存在: {model_path}")

    model = torch.load(model_path, map_location=device, weights_only=False)
    if hasattr(model, "eval"):
        model = model.eval()
    mapping = _load_class_mapping(class_mapping_path)
    _cache[key] = {"model": model, "mapping": mapping}
    while len(_cache) > MAX_CACHE:
        first_key = next(iter(_cache))
        del _cache[first_key]
    return model


def _get_cached_mapping(model_path: str, class_mapping_path: str | None) -> dict:
    key = (model_path, class_mapping_path or "")
    if key in _cache:
        return _cache[key]["mapping"]
    return _load_class_mapping(class_mapping_path)


def evict(model_path: str, class_mapping_path: str | None = None) -> None:
    """部署变更/模型删除时手动清缓存。"""
    key = (model_path, class_mapping_path or "")
    _cache.pop(key, None)


def recognize(
    image: Image.Image,
    model_path: str,
    class_mapping_path: str | None,
    device: str = "cpu",
    top_k: int = 5,
) -> list[dict]:
    """对 PIL 图像执行 top-k 分类，返回 [{label, score}, ...]，label=class_mapping 中的字符串（如 "cat_12"）。"""
    model = load_model(model_path, class_mapping_path, device=device)
    class_mapping = _get_cached_mapping(model_path, class_mapping_path)
    img_tensor = _preprocess(image).unsqueeze(0).to(device)

    with torch.no_grad():
        logits = model(img_tensor)
        probs = torch.softmax(logits, dim=1)
        num_classes = probs.size(1)
        k = min(top_k, num_classes)
        top_probs, top_indices = probs[0].topk(k)

    results: list[dict] = []
    for idx, prob in zip(top_indices.tolist(), top_probs.tolist()):
        label = class_mapping.get(str(idx), f"class_{idx}")
        results.append({"label": label, "score": round(float(prob), 4)})
    return results
