
import re
import time
from typing import Optional
from urllib.parse import quote

from tool import amap_mcp

LOC_TTL_SECONDS = 30 * 60   
CITY = "马鞍山"            
_COORD = re.compile(r"^\d{1,3}\.\d+,\d{1,3}\.\d+$")
_last = {}   
_default_origin = None   

def update_location(user_id: int, lng: float, lat: float) -> None:
    _last[user_id] = (lng, lat, time.time())

def get_location(user_id: int) -> Optional[str]:
    got = _last.get(user_id)
    if got and time.time() - got[2] < LOC_TTL_SECONDS:
        return f"{got[0]},{got[1]}"
    return None

def default_origin() -> str:
    global _default_origin
    if _default_origin is None:
        geo = amap_mcp.geocode("安徽工业大学", city=CITY)
        if geo["ok"]:
            _default_origin = geo["location"]
    return _default_origin or ""

def resolve_dest(target: str) -> tuple:
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
    target = (target or "").strip()
    if not target:
        return {"ok": False, "message": "缺少目的地哦 (´･ω･`) 要去哪儿呀？"}
    reported = origin or get_location(user_id)   
    origin = reported or default_origin()        
    if not origin:
        return {"ok": False, "message": "还不知道你的当前位置呢 (´•̥ω•̥`) 请点击聊天框旁的 📍 定位按钮并允许浏览器定位授权"}
    if _COORD.match(target):
        dest, dest_name = target, "目标地点"
    else:
        dest, dest_name = resolve_dest(target)
        if not dest:
            return {"ok": False, "message": dest_name}   
    got = amap_mcp.route(origin, dest, mode)
    if not got["ok"]:
        return {"ok": False, "message": got["error"]}
    return {"ok": True, "data": {
        "target": target, "destination": dest_name, "mode": mode,
        "used_default_origin": not bool(reported),   
        "distance_km": round(int(got.get("distance") or 0) / 1000, 1),
        "duration_min": max(1, round(int(got.get("duration") or 0) / 60)),
        "steps": got.get("steps") or [],
        "uri": f"https://uri.amap.com/navigation?to={dest}&toName={quote(dest_name)}"
               f"&mode={mode}&policy=1&src=anda&coordinate=gaode&callnative=0",
    }}


NAV_WORDS = ("怎么过去", "怎么去", "怎么走", "如何去", "带我去", "帮我导航", "导航到", "导航去",
             "导航", "规划路线", "规划一下", "路线", "过去怎么", "咋去", "咋走")

def nav_tool(utterance: str, user_id: int, **_) -> dict:
    target = utterance
    for w in sorted(NAV_WORDS, key=len, reverse=True):   
        target = target.replace(w, " ")
    target = re.sub(r"[？?！!。，,的到呢吗吧呀~\s]", "", target)
    if not target:
        return {"ok": False, "error": "没听出目的地呢 (´･ω･`) 试试说：导航到逸夫楼"}
    got = plan(user_id, target)
    if not got["ok"]:
        return {"ok": False, "error": got["message"]}   
    data = got["data"]
    return {"ok": True, "起点": "安徽工业大学（未获取到实时定位，默认用学校位置）" if data["used_default_origin"] else "你的实时位置",
            "目的地": data["destination"], "方式": data["mode"],
            "距离_公里": data["distance_km"], "预计_分钟": data["duration_min"],
            "高德导航链接": data["uri"],
            "路线要点": [s["instruction"] for s in data["steps"][:6]]}
