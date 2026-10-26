# nav_service.py (导航业务) 用户位置上报缓存 + "当前位置→目标地点"路线规划；供路由层复用
import re
import time
from typing import Optional
from urllib.parse import quote

from tool import amap_mcp

LOC_TTL_SECONDS = 30 * 60   # 位置缓存 30 分钟：过期视为失效，要求重新定位
_COORD = re.compile(r"^\d{1,3}\.\d+,\d{1,3}\.\d+$")
_last = {}   # user_id -> (lng, lat, ts) 内存缓存：单进程开发期够用，多 worker 部署时再挪库

def update_location(user_id: int, lng: float, lat: float) -> None:
    _last[user_id] = (lng, lat, time.time())

def get_location(user_id: int) -> Optional[str]:
    got = _last.get(user_id)
    if got and time.time() - got[2] < LOC_TTL_SECONDS:
        return f"{got[0]},{got[1]}"
    return None

def plan(user_id: int, target: str, mode: str = "walk", origin: str = "") -> dict:
    # target 支持"经纬度串"或"地名/楼栋名"（后者先地理编码）；mode: walk/ride/drive
    target = (target or "").strip()
    if not target:
        return {"ok": False, "message": "缺少目的地"}
    origin = origin or get_location(user_id) or ""
    if not origin:
        return {"ok": False, "message": "还不知道你的当前位置：请在导航弹窗里允许浏览器定位授权"}
    if _COORD.match(target):
        dest, dest_name = target, "目标地点"
    else:
        geo = amap_mcp.geocode(target)
        if not geo["ok"]:
            return {"ok": False, "message": geo["error"]}
        dest, dest_name = geo["location"], geo["name"]
    got = amap_mcp.route(origin, dest, mode)
    if not got["ok"]:
        return {"ok": False, "message": got["error"]}
    return {"ok": True, "data": {
        "target": target, "destination": dest_name, "mode": mode,
        "distance_km": round(int(got.get("distance") or 0) / 1000, 1),
        "duration_min": max(1, round(int(got.get("duration") or 0) / 60)),
        "steps": got.get("steps") or [],
        # 高德 URI 导航链接：轻导航面板里"打开高德App实时导航"的跳转地址
        "uri": f"https://uri.amap.com/navigation?to={dest}&toName={quote(dest_name)}"
               f"&mode={mode}&policy=1&src=anda&coordinate=gaode&callnative=0",
    }}
