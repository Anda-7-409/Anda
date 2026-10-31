# amap_mcp.py — 高德地图 REST 客户端（"Web服务"类型 Key）——安答的活地图 (๑•̀ㅂ•́)و✧
# 契约（docs/refactoring.md 3.3；消费方：Backend/service/nav_service.py）：
#   geocode(address, city)    -> {"ok","location":"lng,lat","name"} | {"ok":False,"error"}
#   search_poi(keyword, city) -> {"ok","pois":[{"name","address","location"}]} | {"ok":False,"error"}
#   route(origin, dest, mode) -> {"ok","distance":米,"duration":秒,"steps":[{"instruction"}]} | {"ok":False,"error"}
# mode: walk(默认) / drive / bus / riding
import logging
import re

import requests

from Backend import config

log = logging.getLogger("anda.amap")
_BASE = "https://restapi.amap.com"

def _clean(html: str) -> str:
    return re.sub(r"<[^>]+>", "", html or "").strip()

def geocode(addr: str, city: str = "") -> dict:
    if not config.AMAP_MAPS_API_KEY:
        return {"ok": False, "error": "未配置高德 Key（AMAP_MAPS_API_KEY）"}
    try:
        r = requests.get(f"{_BASE}/v3/geocode/geo",
                         params={"key": config.AMAP_MAPS_API_KEY, "address": addr, "city": city},
                         timeout=10)
        r.raise_for_status()
        geo = (r.json().get("geocodes") or [None])[0]
        if not geo or not geo.get("location"):
            return {"ok": False, "error": f"没有找到「{addr}」的位置"}
        return {"ok": True, "location": geo["location"], "name": geo.get("formatted_address") or addr}
    except Exception as e:
        log.warning("高德地理编码服务挂了 (＞﹏＜)： %s", e)
        return {"ok": False, "error": "地理编码服务异常，请稍后再试"}

def search_poi(q: str, city: str = "") -> dict:
    if not config.AMAP_MAPS_API_KEY:
        return {"ok": False, "error": "未配置高德 Key（AMAP_MAPS_API_KEY）"}
    try:
        r = requests.get(f"{_BASE}/v3/place/text",
                         params={"key": config.AMAP_MAPS_API_KEY, "keywords": q,
                                 "city": city, "offset": 5, "page": 1},
                         timeout=10)
        r.raise_for_status()
        pois = r.json().get("pois") or []
        if not pois:
            return {"ok": False, "error": f"没有找到「{q}」相关地点"}
        return {"ok": True, "pois": [{"name": p.get("name", ""), "address": p.get("address") or "",
                                      "location": p.get("location", "")} for p in pois]}
    except Exception as e:
        log.warning("高德地点搜索服务挂了 (＞﹏＜)： %s", e)
        return {"ok": False, "error": "地点搜索服务异常，请稍后再试"}

def _route_steps(steps: list, *fields: str) -> list:
    # 依次尝试多个字段名取步骤文本：高德不同接口/版本字段不同（新版步行是 instruction，旧版是 html）——同一个家出来的接口，脾气全不一样 (。•́︿•̀。)
    out = []
    for s in steps:
        text = ""
        for f in fields:
            if s.get(f):
                text = _clean(s[f])
                break
        out.append({"instruction": text})
    return out

def route(origin: str, dest: str, mode: str = "walk", city: str = "") -> dict:
    if not config.AMAP_MAPS_API_KEY:
        return {"ok": False, "error": "未配置高德 Key（AMAP_MAPS_API_KEY）"}
    try:
        if mode == "drive":
            r = requests.get(f"{_BASE}/v3/direction/driving",
                             params={"key": config.AMAP_MAPS_API_KEY, "origin": origin,
                                     "destination": dest}, timeout=10)
            r.raise_for_status()
            path = ((r.json().get("route") or {}).get("paths") or [None])[0]
            if not path:
                return {"ok": False, "error": "没有规划到驾车路线"}
            return {"ok": True, "distance": path.get("distance"), "duration": path.get("duration"),
                    "steps": _route_steps(path.get("steps") or [], "instruction")}

        if mode == "bus":
            r = requests.get(f"{_BASE}/v3/direction/transit/integrated",
                             params={"key": config.AMAP_MAPS_API_KEY, "origin": origin,
                                     "destination": dest, "city": city, "strategy": 0}, timeout=10)
            r.raise_for_status()
            transits = ((r.json().get("route") or {}).get("transits") or [None])
            transit = next((t for t in transits if t), None)
            if not transit:
                return {"ok": False, "error": "没有规划到公交路线"}
            steps = []
            for seg in transit.get("segments") or []:
                for s in (seg.get("walking") or {}).get("steps") or []:
                    steps.append({"instruction": _clean(s.get("html", ""))})
                for line in (seg.get("bus") or {}).get("buslines") or []:
                    steps.append({"instruction": f"乘坐 {line.get('name', '')}"})
            return {"ok": True, "distance": transit.get("walking_distance"),
                    "duration": transit.get("duration"), "steps": steps}

        if mode == "riding":
            # 高德 v4 接口：返回结构是 {"errcode":0,"data":{"paths":[...]}}（和 v3 完全两套长相，别问，问就是历史包袱 (＞﹏＜)）
            r = requests.get(f"{_BASE}/v4/direction/electrobike",
                             params={"key": config.AMAP_MAPS_API_KEY, "origin": origin,
                                     "destination": dest}, timeout=10)
            r.raise_for_status()
            path = ((r.json().get("data") or {}).get("paths") or [None])[0]
            if not path:
                return {"ok": False, "error": "没有规划到骑行路线"}
            return {"ok": True, "distance": path.get("distance"), "duration": path.get("duration"),
                    "steps": _route_steps(path.get("steps") or [], "instruction")}

        # 默认步行：步骤文本优先 instruction 字段，旧版接口回落到 html（带 <b> 标签，需清洗——导航步骤里蹦 HTML，也就高德干得出来）
        r = requests.get(f"{_BASE}/v3/direction/walking",
                         params={"key": config.AMAP_MAPS_API_KEY, "origin": origin,
                                 "destination": dest}, timeout=10)
        r.raise_for_status()
        path = ((r.json().get("route") or {}).get("paths") or [None])[0]
        if not path:
            return {"ok": False, "error": "没有规划到步行路线"}
        return {"ok": True, "distance": path.get("distance"), "duration": path.get("duration"),
                "steps": _route_steps(path.get("steps") or [], "instruction", "html")}
    except Exception as e:
        log.warning("高德路线规划服务挂了 (＞﹏＜)： %s", e)
        return {"ok": False, "error": "路线规划服务异常，请稍后再试"}
