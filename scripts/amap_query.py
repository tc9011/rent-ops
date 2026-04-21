#!/usr/bin/env python3
"""高德 Web 服务查询 CLI — 为 agent 在评估房源时调用而设计。

三个子命令：
- commute         通勤查询：目标地址 ← profile.work_location，输出耗时 + 换乘 + 1-5 分
- poi             周边 POI：按 amap.yml 里的命名类别搜
- convenience     多类别加权便利分：输出 1-5 分 + 每类明细

输出全部是 JSON（--pretty 会 indent），方便 agent 直接解析。

示例：
    python3 scripts/amap_query.py commute --to "望京SOHO"
    python3 scripts/amap_query.py commute --to "望京SOHO" --mode driving
    python3 scripts/amap_query.py poi --location "望京SOHO" --category metro
    python3 scripts/amap_query.py convenience --location "望京SOHO"
    python3 scripts/amap_query.py convenience --location "116.48,39.99"

--city 未指定时从 config/profile.yml 读。
--from 未指定时使用 profile.yml 的 work_location。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.lib.amap import AmapClient, load_amap_config
from scripts.lib.city import (
    active_city,
    load_city,
    flatten_areas,
    CityNotFoundError,
)

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_PATH = REPO_ROOT / "config" / "profile.yml"


def _load_profile() -> dict:
    if not PROFILE_PATH.exists():
        return {}
    with PROFILE_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _resolve_city(explicit: str | None) -> dict:
    try:
        return load_city(explicit) if explicit else active_city()
    except CityNotFoundError as e:
        sys.stderr.write(f"city error: {e}\n")
        sys.exit(2)


def _coord(
    client: AmapClient, text: str, city: dict,
) -> tuple[float, float] | None:
    """解析顺序：坐标字符串 → 城市片区查表 → geocode → PlaceSearch 兜底。

    city 片区查表优先级最高：如果 text 精确命中 cities/{pinyin}.yml
    的 areas 或 sub_areas 名，直接用 yml 里预设的坐标，避免 Amap 把
    "科技园" 误解析到其他城市或错误商圈。
    """
    if "," in text:
        try:
            lng, lat = text.split(",")
            return float(lng), float(lat)
        except ValueError:
            pass
    # 查当前城市片区表
    areas = flatten_areas(city)
    if text in areas and areas[text].get("pos"):
        pos = areas[text]["pos"]
        return pos[0], pos[1]
    # 综合解析（geocode + PlaceSearch 兜底）
    r = client.resolve_location(text, city.get("amap_city_name", ""))
    if r.get("status") != "ok":
        return None
    return r["lng"], r["lat"]


# ─── commute ─────────────────────────────────────────────────────────────────
def _commute_score(duration_min: float, transfers: int) -> float:
    """_shared.md 通勤评分口径映射为 1-5 分。"""
    if duration_min <= 20:
        base = 5.0
    elif duration_min <= 30:
        base = 4.0
    elif duration_min <= 45:
        base = 3.0
    elif duration_min <= 60:
        base = 2.0
    else:
        base = 1.0
    # 换乘 ≥ 2 次扣 0.5
    if transfers >= 2:
        base -= 0.5
    return max(1.0, round(base, 1))


def _route_one(
    client: AmapClient, city: dict,
    origin: tuple[float, float], destination: tuple[float, float], mode: str,
) -> dict[str, Any]:
    """单段路径查询，输出标准字段 + score_5。"""
    if mode == "transit":
        route = client.route_transit(origin, destination, city["amap_city_name"])
    elif mode == "driving":
        route = client.route_driving(origin, destination)
    elif mode == "walking":
        route = client.route_walking(origin, destination)
    elif mode == "bicycling":
        route = client.route_bicycling(origin, destination)
    else:
        return {"status": "error", "message": f"unknown mode: {mode}"}
    if route.get("status") != "ok":
        return route
    route["score_5"] = _commute_score(
        route["duration_min"], route.get("transfers", 0),
    )
    return route


def _anchors_from_profile(profile: dict) -> list[dict[str, Any]]:
    """从 profile.yml 读 anchors（向后兼容 work_location）。格式和 build_city_runtime._build_anchors 一致。"""
    # 复用 build_city_runtime 的逻辑，避免口径漂移
    from scripts.build_city_runtime import _build_anchors
    anchors, _warnings = _build_anchors(profile)
    return anchors


def cmd_commute(args) -> dict[str, Any]:
    city = _resolve_city(args.city)
    client = AmapClient()
    if client.disabled:
        return {"status": "disabled", "reason": client.config.get("reason"),
                "fallback_hint": "用 WebSearch 搜 '{工作地} 到 {小区} 地铁' 估算"}

    d = _coord(client, args.to, city)
    if not d:
        return {"status": "error", "message": f"destination 解析失败: {args.to}"}

    # ── 单点 legacy 模式：显式 --from ──
    if args.from_:
        o = _coord(client, args.from_, city)
        if not o:
            return {"status": "error", "message": f"origin 解析失败: {args.from_}"}
        r = _route_one(client, city, o, d, args.mode)
        if r.get("status") != "ok":
            return {"status": r.get("status", "error"),
                    "message": r.get("message"),
                    "mode": args.mode, "origin": args.from_, "destination": args.to}
        return {
            "status": "ok",
            "mode": args.mode,
            "origin": args.from_,
            "destination": args.to,
            "duration_min": r["duration_min"],
            "distance_m": r["distance_m"],
            "transfers": r.get("transfers", 0),
            "walking_distance_m": r.get("walking_distance_m"),
            "cost_cny": r.get("cost_cny"),
            "tolls_cny": r.get("tolls_cny"),
            "score_5": r["score_5"],
        }

    # ── 多锚点模式：读 profile ──
    profile = _load_profile()
    anchors = _anchors_from_profile(profile)
    if not anchors:
        return {"status": "error",
                "message": "profile.yml 没有 anchors，也没有 work_location。"
                           "请参考 config/profile.example.yml 配置锚点。"}

    per_anchor_results = []
    total_weight = 0.0
    weighted_sum = 0.0
    for a in anchors:
        o = _coord(client, a["address"], city)
        if not o:
            per_anchor_results.append({
                "name": a["name"], "mode": a["mode"], "icon": a["icon"],
                "importance": a["importance"],
                "status": "error",
                "message": f"address 解析失败: {a['address']}",
            })
            continue
        # 如果 args.mode 被显式指定（非默认 transit），覆盖锚点 mode
        mode = args.mode if args.mode != "transit" or args.from_ else a["mode"]
        # 更清晰：mode 默认跟随锚点；只有用户显式给 --mode 非 transit 或非默认，才覆盖
        # 为简单起见，不覆盖；尊重 anchor.mode
        mode = a["mode"]
        r = _route_one(client, city, o, d, mode)
        if r.get("status") != "ok":
            per_anchor_results.append({
                "name": a["name"], "mode": mode, "icon": a["icon"],
                "importance": a["importance"],
                "status": r.get("status", "error"),
                "message": r.get("message"),
            })
            continue
        per_anchor_results.append({
            "name": a["name"], "mode": mode, "icon": a["icon"],
            "importance": a["importance"],
            "status": "ok",
            "duration_min": r["duration_min"],
            "distance_m": r["distance_m"],
            "transfers": r.get("transfers", 0),
            "walking_distance_m": r.get("walking_distance_m"),
            "score_5": r["score_5"],
            "over_max": r["duration_min"] > a["max_minutes"],
            "max_minutes": a["max_minutes"],
        })
        weighted_sum += r["score_5"] * a["importance"]
        total_weight += a["importance"]

    if total_weight == 0:
        return {
            "status": "error",
            "message": "所有锚点路径查询都失败了",
            "anchors": per_anchor_results,
            "destination": args.to,
        }

    aggregate = round(weighted_sum / total_weight, 1)
    return {
        "status": "ok",
        "mode": "multi-anchor",
        "destination": args.to,
        "anchors": per_anchor_results,
        "aggregate_score_5": aggregate,
    }


# ─── poi ─────────────────────────────────────────────────────────────────────
def cmd_poi(args) -> dict[str, Any]:
    city = _resolve_city(args.city)
    amap_cfg = load_amap_config()
    if amap_cfg.get("disabled"):
        return {"status": "disabled", "reason": amap_cfg.get("reason")}
    client = AmapClient(config=amap_cfg)

    loc = _coord(client, args.location, city)
    if not loc:
        return {"status": "error", "message": f"location 解析失败: {args.location}"}

    # 解析类别
    categories = ((amap_cfg.get("convenience") or {}).get("categories")) or {}
    if args.category:
        if args.category not in categories:
            return {"status": "error",
                    "message": f"类别 {args.category} 未在 amap.yml 定义。可选: {list(categories)}"}
        cat = categories[args.category]
        result = client.search_around(
            loc,
            types=cat.get("type", ""),
            radius=cat.get("max_radius_m") or args.radius,
            page_size=args.top or 20,
        )
        result["category"] = args.category
        result["category_name"] = cat.get("name")
        return result

    # 无 --category：用 --type / --keywords
    return client.search_around(
        loc, types=args.type or "", keywords=args.keywords or "",
        radius=args.radius, page_size=args.top or 20,
    )


# ─── convenience ─────────────────────────────────────────────────────────────
def cmd_convenience(args) -> dict[str, Any]:
    city = _resolve_city(args.city)
    amap_cfg = load_amap_config()
    if amap_cfg.get("disabled"):
        return {"status": "disabled", "reason": amap_cfg.get("reason"),
                "fallback_hint": "用 WebSearch 了解周边配套"}

    client = AmapClient(config=amap_cfg)
    loc = _coord(client, args.location, city)
    if not loc:
        return {"status": "error", "message": f"location 解析失败: {args.location}"}

    conv = amap_cfg.get("convenience") or {}
    categories = conv.get("categories") or {}
    default_radius = int(conv.get("radius_m") or 500)
    if not categories:
        return {"status": "error",
                "message": "amap.yml 中未配置 convenience.categories"}

    raw_score = 0.0
    max_raw = 0.0
    breakdown: dict[str, Any] = {}

    for key, cat in categories.items():
        radius = int(cat.get("max_radius_m") or default_radius)
        r = client.search_around(
            loc, types=cat.get("type", ""), radius=radius, page_size=20,
        )
        if r.get("status") != "ok":
            breakdown[key] = {"status": r.get("status"), "message": r.get("message")}
            # 不把失败纳入 max_raw 计算，保持相对公平
            continue
        count = r.get("count", 0)
        nearest = r["pois"][0]["distance_m"] if r.get("pois") else None
        cap = int(cat.get("cap_count") or 5)
        weight = float(cat.get("weight") or 1.0)
        got = min(count, cap)
        raw_score += got * weight
        max_raw += cap * weight
        breakdown[key] = {
            "name": cat.get("name", key),
            "count": count,
            "capped_count": got,
            "weight": weight,
            "radius_m": radius,
            "nearest_m": nearest,
            "top3": [
                {"name": p["name"], "distance_m": p["distance_m"]}
                for p in (r.get("pois") or [])[:3]
            ],
        }

    if max_raw == 0:
        score_5 = 1.0
    else:
        score_5 = round(raw_score / max_raw * 5, 1)
        score_5 = max(1.0, min(5.0, score_5))

    return {
        "status": "ok",
        "location": args.location,
        "resolved_coord": f"{loc[0]},{loc[1]}",
        "city": city["name"],
        "score_5": score_5,
        "raw_score": round(raw_score, 2),
        "max_raw": round(max_raw, 2),
        "breakdown": breakdown,
    }


# ─── main ────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(
        description="高德 Web 服务查询（通勤 / POI / 便利分）"
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    # 共享的 --pretty / --city 放每个子命令上，避免顺序问题
    def _common(sp):
        sp.add_argument("--pretty", action="store_true", help="pretty-print JSON")
        sp.add_argument("--city", help="城市名或拼音；默认读 profile.yml")

    p_c = sub.add_parser("commute", help="通勤查询")
    _common(p_c)
    p_c.add_argument("--from", dest="from_", help="出发地（默认 profile.yml work_location）")
    p_c.add_argument("--to", required=True, help="目的地（小区名或 lng,lat）")
    p_c.add_argument("--mode", default="transit",
                     choices=["transit", "driving", "walking", "bicycling"])

    p_p = sub.add_parser("poi", help="周边 POI 搜索")
    _common(p_p)
    p_p.add_argument("--location", required=True, help="中心点（地址文本或 lng,lat）")
    p_p.add_argument("--category",
                     help="使用 amap.yml 里定义的命名类别（如 supermarket）")
    p_p.add_argument("--type", help="直接传高德 POI type 代码")
    p_p.add_argument("--keywords", help="关键词搜索")
    p_p.add_argument("--radius", type=int, default=1000)
    p_p.add_argument("--top", type=int, default=20)

    p_v = sub.add_parser("convenience", help="加权便利分")
    _common(p_v)
    p_v.add_argument("--location", required=True, help="小区名或 lng,lat")

    args = parser.parse_args()

    if args.cmd == "commute":
        out = cmd_commute(args)
    elif args.cmd == "poi":
        out = cmd_poi(args)
    elif args.cmd == "convenience":
        out = cmd_convenience(args)
    else:
        parser.error("unknown cmd")
        return

    if args.pretty:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(out, ensure_ascii=False))
    sys.exit(0 if out.get("status") == "ok" else 1)


if __name__ == "__main__":
    main()
