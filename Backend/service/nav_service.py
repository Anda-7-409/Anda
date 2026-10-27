# nav_service.py (导航业务) 用户位置上报缓存 + "当前位置→目标地点"路线规划；供路由层复用
import re
import time
from typing import Optional
from urllib.parse import quote

from tool import amap_mcp

LOC_TTL_SECONDS = 30 * 60   # 位置缓存 30 分钟：过期视为失效，要求重新定位
CITY = "马鞍山"             # 校园应用：目的地/默认起点优先在本市范围内找，避免"逸夫楼"匹配到外市
_COORD = re.compile(r"^\d{1,3}\.\d+,\d{1,3}\.\d+$")
_last = {}   # user_id -> (lng, lat, ts) 内存缓存：单进程开发期够用，多 worker 部署时再挪库
_default_origin = None   # "安徽工业大学"坐标缓存（None=还没查过）

def update_location(user_id: int, lng: float, lat: float) -> None:
    _last[user_id] = (lng, lat, time.time())

def get_location(user_id: int) -> Optional[str]:
    got = _last.get(user_id)
    if got and time.time() - got[2] < LOC_TTL_SECONDS:
        return f"{got[0]},{got[1]}"
    return None

def default_origin() -> str:
    # 兜底起点：浏览器拿不到定位时（台式机无 GPS/WiFi 定位源很常见）用学校位置，保证问路不被卡死
    global _default_origin
    if _default_origin is None:
        geo = amap_mcp.geocode("安徽工业大学", city=CITY)
        if geo["ok"]:
            _default_origin = geo["location"]
    return _default_origin or ""

def resolve_dest(target: str) -> tuple:
    # 目的地解析：POI 搜索（楼栋/地标，优先校内命中）→ 地理编码（本市 → 全国，覆盖跨市车站等）
    got = amap_mcp.search_poi(target, city=CITY)
    if got["ok"]:
        pick = next((p for p in got["pois"] if "安徽工业大学" in p["name"] + p["address"]),
                    got["pois"][0])
        return pick["location"], pick["name"]
    geo = amap_mcp.geocode(target, city=CITY)
    if not geo["ok"]:
        geo = amap_mcp.geocode(target)
    if not geo["ok"]:
        return "", geo["error"]
    return geo["location"], geo["name"]

def plan(user_id: int, target: str, mode: str = "walk", origin: str = "") -> dict:
    # target 支持"经纬度串"或"地名/楼栋名"（后者先地理编码）；mode: walk/ride/drive
    target = (target or "").strip()
    if not target:
        return {"ok": False, "message": "缺少目的地"}
    reported = origin or get_location(user_id)   # 显式传入 > 30分钟内上报的实时定位
    origin = reported or default_origin()        # 都没有 → 学校默认起点兜底
    if not origin:
        return {"ok": False, "message": "还不知道你的当前位置：请点击聊天框旁的 📍 定位按钮并允许浏览器定位授权"}
    if _COORD.match(target):
        dest, dest_name = target, "目标地点"
    else:
        dest, dest_name = resolve_dest(target)
        if not dest:
            return {"ok": False, "message": dest_name}   # 解析失败时这里装的是错误信息
    got = amap_mcp.route(origin, dest, mode)
    if not got["ok"]:
        return {"ok": False, "message": got["error"]}
    return {"ok": True, "data": {
        "target": target, "destination": dest_name, "mode": mode,
        "used_default_origin": not bool(reported),   # 告诉上层：起点是兜底位置还是实时定位
        "distance_km": round(int(got.get("distance") or 0) / 1000, 1),
        "duration_min": max(1, round(int(got.get("duration") or 0) / 60)),
        "steps": got.get("steps") or [],
        # 高德 URI 导航链接：轻导航面板里"打开高德App实时导航"的跳转地址
        "uri": f"https://uri.amap.com/navigation?to={dest}&toName={quote(dest_name)}"
               f"&mode={mode}&policy=1&src=anda&coordinate=gaode&callnative=0",
    }}


NAV_WORDS = ("怎么过去", "怎么去", "怎么走", "如何去", "带我去", "帮我导航", "导航到", "导航去",
             "导航", "规划路线", "规划一下", "路线", "过去怎么", "咋去", "咋走")

def nav_tool(utterance: str, user_id: int, **_) -> dict:
    # 从用户原话里抠出目的地：删掉导航动词 → 再删疑问词/标点 → 剩下的当地名（orchestrator 的 fn 契约）
    target = utterance
    for w in sorted(NAV_WORDS, key=len, reverse=True):   # 长词优先，防"导航到"被"导航"先吃掉
        target = target.replace(w, " ")
    target = re.sub(r"[？?！!。，,的到呢吗吧呀~\s]", "", target)
    if not target:
        return {"ok": False, "error": "没听出目的地~ 试试：导航到逸夫楼"}
    got = plan(user_id, target)
    if not got["ok"]:
        return {"ok": False, "error": got["message"]}   # 如"还不知道你的当前位置"，如实透传给模型
    data = got["data"]
    return {"ok": True, "起点": "安徽工业大学（未获取到实时定位，默认用学校位置）" if data["used_default_origin"] else "你的实时位置",
            "目的地": data["destination"], "方式": data["mode"],
            "距离_公里": data["distance_km"], "预计_分钟": data["duration_min"],
            "高德导航链接": data["uri"],
            "路线要点": [s["instruction"] for s in data["steps"][:6]]}
