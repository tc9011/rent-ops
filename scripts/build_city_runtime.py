#!/usr/bin/env python3
"""生成 data/city-runtime.json — 给 map-view.html / listings-view.html 消费。

合并 config/profile.yml + cities/{pinyin}.yml 的数据，扁平化 areas，输出单个 JSON。
map-view.html 启动时 fetch 这个文件就拿到当前城市的所有上下文。

用法：
  python3 scripts/build_city_runtime.py                   # 读 profile 里的 city
  python3 scripts/build_city_runtime.py --city beijing    # 指定城市
  python3 scripts/build_city_runtime.py --out path.json   # 指定输出路径
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.lib.city import (
    active_city,
    load_city,
    flatten_areas,
    CityNotFoundError,
)

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = REPO_ROOT / "data" / "city-runtime.json"
PROFILE_PATH = REPO_ROOT / "config" / "profile.yml"

SCHEMA_VERSION = 2

# icon 推断关键词表（顺序重要，先匹配长词）
ICON_RULES: list[tuple[tuple[str, ...], str]] = [
    (("幼儿园",), "🏫"),
    (("小学", "中学", "大学", "学校", "school"), "🏫"),
    (("医院", "诊所", "hospital"), "🏥"),
    (("健身", "gym", "瑜伽", "fitness"), "💪"),
    (("父母", "老家"), "🏠"),
    (("家", "home"), "🏠"),
    (("公司", "工作", "办公室", "office", "work"), "🏢"),
    (("合作", "客户", "partner"), "💼"),
    (("商场", "超市", "购物", "shopping", "mall"), "🛍️"),
]
DEFAULT_ICON = "📍"

VALID_MODES = {"transit", "driving", "walking", "bicycling"}


def _load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    with PROFILE_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def infer_icon(name: str) -> str:
    """按 anchor.name 里的关键词推断 icon。"""
    low = name.lower()
    for keywords, icon in ICON_RULES:
        for kw in keywords:
            if kw in low or kw in name:
                return icon
    return DEFAULT_ICON


def _build_anchors(profile: dict) -> tuple[list[dict[str, Any]], list[str]]:
    """返回 (anchors, warnings)。

    - 有 anchors 数组 → 用它（normalize 字段）
    - 无 anchors 但有 work_location → 自动迁移成单锚点 + deprecation warning
    - 两者都有 → anchors 胜 + conflict warning
    - 两者都无 → 返回空列表
    """
    warnings: list[str] = []
    raw_anchors = profile.get("anchors")
    legacy = profile.get("work_location")
    commute = profile.get("commute") or {}
    default_mode = {
        "地铁": "transit", "transit": "transit",
        "公交": "transit",
        "骑行": "bicycling", "bicycling": "bicycling",
        "步行": "walking", "walking": "walking",
        "开车": "driving", "driving": "driving",
    }.get(commute.get("transport") or "", "transit")
    default_max = int(commute.get("max_minutes") or 45)

    if raw_anchors and legacy:
        warnings.append(
            "profile.yml 同时有 anchors 和 work_location — 使用 anchors，忽略 work_location"
        )

    if raw_anchors:
        anchors = []
        for i, a in enumerate(raw_anchors):
            if not isinstance(a, dict):
                warnings.append(f"anchors[{i}] 不是对象，跳过")
                continue
            name = (a.get("name") or "").strip()
            address = (a.get("address") or "").strip()
            if not name or not address:
                warnings.append(f"anchors[{i}] 缺少 name 或 address，跳过")
                continue
            mode = a.get("mode") or default_mode
            if mode not in VALID_MODES:
                warnings.append(
                    f"anchors[{i}] mode='{mode}' 不是 {VALID_MODES} 之一，改 transit"
                )
                mode = "transit"
            icon = a.get("icon") or infer_icon(name)
            anchors.append({
                "name": name,
                "address": address,
                "mode": mode,
                "max_minutes": int(a.get("max_minutes") or default_max),
                "importance": int(a.get("importance") or 3),
                "icon": icon,
                "pos": None,  # map-view.html 启动时客户端 geocode
            })
        return anchors, warnings

    if legacy:
        warnings.append(
            "profile.yml 使用了旧的 work_location 字段 — 已自动迁移为单锚点。"
            "建议改用 anchors 数组（见 config/profile.example.yml）"
        )
        return [{
            "name": "工作地",
            "address": legacy,
            "mode": default_mode,
            "max_minutes": default_max,
            "importance": 5,
            "icon": "🏢",
            "pos": None,
        }], warnings

    return [], warnings


def build(city: dict, profile: dict) -> dict:
    areas = flatten_areas(city)
    budget = profile.get("budget") or {}
    anchors, warnings = _build_anchors(profile)

    # 向后兼容：保留 work_location 字段（取第一个锚点的 label）
    work_label = anchors[0]["address"] if anchors else profile.get("work_location")

    return {
        "schema_version": SCHEMA_VERSION,
        "city": {
            "name": city.get("name"),
            "pinyin": city.get("pinyin"),
            "code": city.get("code"),
            "center": city.get("center"),
            "amap_city_name": city.get("amap_city_name") or city.get("name"),
        },
        "areas": areas,
        "area_order": list(areas.keys()),
        "anchors": anchors,
        "work_location": {
            # v1 兼容字段。新代码请读 anchors[0]
            "label": work_label,
        },
        "profile": {
            "budget_min": budget.get("min"),
            "budget_max": budget.get("max"),
            "type": profile.get("type"),
            "rooms": profile.get("rooms") or [],
        },
        "_warnings": warnings,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--city")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    try:
        city = load_city(args.city) if args.city else active_city()
    except CityNotFoundError as e:
        print(f"✗ {e}", file=sys.stderr)
        sys.exit(1)

    profile = _load_profile()
    runtime = build(city, profile)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(runtime, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    area_count = len(runtime["areas"])
    anchor_count = len(runtime["anchors"])
    print(
        f"✓ 写入 {args.out}  城市={runtime['city']['name']}"
        f"  areas={area_count}  anchors={anchor_count}"
    )
    for w in runtime.get("_warnings") or []:
        print(f"  ⚠ {w}", file=sys.stderr)


if __name__ == "__main__":
    main()
