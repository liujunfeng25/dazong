#!/usr/bin/env python3
"""Validate project documentation against the running API and Vue Router."""

from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OPENAPI_URL = "http://127.0.0.1:8000/openapi.json"

DOC_PATHS = [
    ROOT / "README.md",
    ROOT / "frontend" / "README.md",
    ROOT / "demo-console" / "README.md",
    ROOT / "docs",
    ROOT.parent / "smart-scale-android" / "README.md",
    ROOT.parent / "sorter-pda-android" / "README.md",
    ROOT.parent / "driver-android" / "README.md",
]

FORBIDDEN = {
    "/api/supplier/picking": "旧供货方配货接口",
    "/api/supplier/inventory": "不存在的供货方库存接口",
    "/api/factory/intake": "不存在的工厂进厂接口",
    "/api/factory/jobs": "不存在的工厂加工工单接口",
    "/api/delivery/tasks": "不存在的旧配送任务接口",
    "/api/monitor/snapshot": "不存在的旧监管快照接口",
    "/api/monitor/vehicles": "不存在的旧监管车辆接口",
    "/api/tianshu/insights": "不存在的旧天枢接口",
    "DRAFT → PENDING": "旧英文订单状态机",
    "DRAFT -> PENDING": "旧英文订单状态机",
    "smart-scale-uniapp": "已退出现行架构的旧智能秤项目",
    "阶段四": "过期阶段名称",
    "路线规划（Mock）": "过期 Mock 描述",
}

API_RE = re.compile(r"/api/[A-Za-z0-9_{}:.*\-/]+")
PAGE_RE = re.compile(r"(?<![A-Za-z0-9])/(operation|client|supplier|delivery|factory|monitor)(?:/[A-Za-z0-9_{}:.\-/]+)?")
MD_LINK_RE = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    out: list[Path] = []
    for path in DOC_PATHS:
        if path.is_file():
            out.append(path)
        elif path.is_dir():
            out.extend(sorted(path.rglob("*.md")))
    return out


def normalize_route(path: str) -> str:
    value = path.split("?", 1)[0].rstrip(".,;:，。；：）)")
    value = re.sub(r"\{[^}/]+\}", "{}", value)
    value = re.sub(r":[A-Za-z_][A-Za-z0-9_]*", "{}", value)
    return value.rstrip("/") or "/"


def load_openapi_paths() -> set[str]:
    try:
        with urllib.request.urlopen(OPENAPI_URL, timeout=5) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"无法读取 {OPENAPI_URL}；请先启动后端再运行 docs-check: {exc}"
        ) from exc
    return {normalize_route(path) for path in payload.get("paths", {})}


def parse_frontend_routes() -> set[str]:
    router = ROOT / "frontend" / "src" / "router" / "index.js"
    routes: set[str] = set()
    current_parent = ""
    top_re = re.compile(r"^    path: '(/[^']+)'")
    child_re = re.compile(r"^\s+\{\s*path: '([^']+)'")
    multiline_child_re = re.compile(r"^\s{6,}path: '([^']+)'")
    for line in router.read_text(encoding="utf-8").splitlines():
        top = top_re.search(line)
        if top:
            current_parent = top.group(1).rstrip("/")
            routes.add(normalize_route(current_parent))
            continue
        child = child_re.search(line) or multiline_child_re.search(line)
        if current_parent and child:
            rel = child.group(1)
            if rel.startswith("/"):
                routes.add(normalize_route(rel))
            elif rel:
                routes.add(normalize_route(f"{current_parent}/{rel}"))
            else:
                routes.add(normalize_route(current_parent))
    return routes


def check_links(files: list[Path], errors: list[str]) -> None:
    for file in files:
        text = file.read_text(encoding="utf-8")
        for raw in MD_LINK_RE.findall(text):
            target = raw.strip().split("#", 1)[0]
            if not target or "://" in target or target.startswith(("mailto:", "#")):
                continue
            candidate = (file.parent / target).resolve()
            if not candidate.exists():
                errors.append(f"{file}: Markdown 链接不存在: {raw}")


def check_forbidden(files: list[Path], errors: list[str]) -> None:
    for file in files:
        text = file.read_text(encoding="utf-8")
        for needle, label in FORBIDDEN.items():
            if needle in text:
                errors.append(f"{file}: 包含{label}: {needle}")


def check_api(files: list[Path], openapi: set[str], errors: list[str]) -> None:
    for file in files:
        text = file.read_text(encoding="utf-8")
        for raw in sorted(set(API_RE.findall(text))):
            if "*" in raw:
                continue
            normalized = normalize_route(raw)
            if normalized not in openapi:
                errors.append(f"{file}: OpenAPI 中不存在: {raw}")


def check_pages(files: list[Path], routes: set[str], errors: list[str]) -> None:
    ignored = {
        "/client",
        "/supplier",
        "/delivery",
        "/factory",
        "/operation",
        "/monitor",
    }
    for file in files:
        text = file.read_text(encoding="utf-8")
        for raw in sorted(set(match.group(0) for match in PAGE_RE.finditer(text))):
            normalized = normalize_route(raw)
            if normalized in ignored:
                continue
            if normalized not in routes:
                errors.append(f"{file}: Vue Router 中不存在: {raw}")


def check_rag_sources(errors: list[str]) -> None:
    source = ROOT / "backend" / "services" / "ai_chat" / "rag" / "indexer.py"
    text = source.read_text(encoding="utf-8")
    entries = re.findall(r'\("([^"]+\.md)",\s*"[^"]+",\s*"[ABC]"\)', text)
    if not entries:
        errors.append(f"{source}: 未找到 RAG INDEX_SOURCES")
        return
    for rel in entries:
        if not rel.startswith("操作手册/"):
            errors.append(f"{source}: RAG 非操作手册来源: {rel}")
        if not (ROOT / "docs" / rel).is_file():
            errors.append(f"{source}: RAG 来源不存在: {rel}")


def main() -> int:
    files = markdown_files()
    errors: list[str] = []
    try:
        openapi = load_openapi_paths()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        return 1
    routes = parse_frontend_routes()
    check_links(files, errors)
    check_forbidden(files, errors)
    check_api(files, openapi, errors)
    check_pages(files, routes, errors)
    check_rag_sources(errors)

    if errors:
        print("文档一致性检查失败：")
        for error in errors:
            print(f"- {error}")
        return 1

    print(
        f"文档一致性检查通过：{len(files)} 个 Markdown，"
        f"{len(openapi)} 个 OpenAPI 路径，{len(routes)} 个前端路由。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
