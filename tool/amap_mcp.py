# tool/amap_mcp.py (高德地图 MCP 工具链) 地理编码 + 路径规划：主路 MCP Server，REST 直连兜底

# 端点：https://mcp.amap.com/mcp?key=KEY （官方 Streamable HTTP；SSE 版已于 2026-03 下线）

# 降级链路：MCP tools/call → 高德 REST v3/v4 直连（同一把"Web服务"Key）→ 结构化错误（不编造路线）
import json
import re
import threading
import time

import requests

from Backend.config import AMAP_MAPS_API_KEY

MCP_URL = "https://mcp.amap.com/mcp"
TIMEOUT = 15
MODE_TOOLS = {   # mode → (MCP 工具名·坐标版, REST 兜底端点)，两端点同一把 Key
    "walk": ("maps_direction_walking_by_coordinates", "https://restapi.amap.com/v3/direction/walking"),
    "ride": ("maps_bicycling_by_coordinates", "https://restapi.amap.com/v4/direction/bicycling"),
    "drive": ("maps_direction_driving_by_coordinates", "https://restapi.amap.com/v3/direction/driving"),
}
_lock = threading.Lock()
_session = {"id": None, "ts": 0.0}   # MCP 会话缓存：initialize 握手一次复用 30 分钟，失效自动重建

def _post(payload: dict, session_id: str = ""):
    headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if session_id:
        headers["mcp-session-id"] = session_id
    return requests.post(f"{MCP_URL}?key={AMAP_MAPS_API_KEY}", json=payload, headers=headers, timeout=TIMEOUT)

def _frames(resp) -> list:
    # Streamable HTTP 响应可能是 JSON 或 SSE 帧（data: {...}），统一抽出 JSON 对象列表
    text = resp.text.lstrip()
    if "text/event-stream" in resp.headers.get("content-type", "") or text.startswith(("event:", "data:")):
        out = []
        for line in resp.text.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    out.append(json.loads(line[5:].strip()))
                except ValueError:
                    pass
        return out
    try:
        return [resp.json()]
    except ValueError:
        return []

def _ensure_session(force: bool = False) -> str:
    # JSON-RPC 握手：initialize → notifications/initialized；会话 id 存 header mcp-session-id
    with _lock:
        if not force and _session["id"] and time.time() - _session["ts"] < 1800:
            return _session["id"]
        resp = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                      "params": {"protocolVersion": "2025-03-26", "capabilities": {},
                                 "clientInfo": {"name": "anda-agent", "version": "0.1"}}})
        resp.raise_for_status()
        sid = resp.headers.get("mcp-session-id") or ""
        if sid:
            _post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
        _session.update(id=sid, ts=time.time())
        return sid

def _rpc(method: str, params: dict, request_id: int) -> dict:
    # 带一次会话失效自愈：404（服务端会话过期）→ 强制重建握手再试
    for attempt in (1, 2):
        sid = _ensure_session(force=(attempt == 2))
        resp = _post({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}, sid)
        if resp.status_code == 404 and attempt == 1:
            continue
        resp.raise_for_status()
        for frame in _frames(resp):
            if frame.get("id") == request_id:
                if "error" in frame:
                    raise RuntimeError(str(frame["error"])[:120])
                return frame.get("result") or {}
        raise RuntimeError("MCP 响应里没有对应的 result")

def _call_tool(name: str, args: dict) -> dict:
    # tools/call 并解析 result.content[].text 里的 JSON（高德 MCP 返回 JSON 字符串）
    result = _rpc("tools/call", {"name": name, "arguments": args}, request_id=2)
    if result.get("isError"):
        raise RuntimeError(str(result.get("content"))[:120])
    raw = "\n".join(c.get("text", "") for c in (result.get("content") or []) if c.get("type") == "text").strip()
    l, r = raw.find("{"), raw.rfind("}")
    if l != -1 and r > l:
        try:
            return json.loads(raw[l:r + 1])
        except ValueError:
            pass
    return {"raw": raw[:500]}

def _check_key() -> str:
    if not AMAP_MAPS_API_KEY:
        return "未配置高德 Key（.env: AMAP_MAPS_API_KEY，需\"Web服务\"类型）"
    return ""

def geocode(address: str, city: str = "") -> dict:
    # 地址/楼栋名 → 经纬度；MCP 主路失败自动走 REST v3 兜底
    bad = _check_key()
    if bad:
        return {"ok": False, "error": bad}
    address = (address or "").strip()
    if not address:
        return {"ok": False, "error": "地点为空"}

    def _dig(data):
        if not isinstance(data, dict):
            return None
        loc = str(data.get("location") or "")
        if re.match(r"^\d{1,3}\.\d+,\d{1,3}\.\d+$", loc):
            return {"location": loc, "name": data.get("formatted_address") or address}
        for g in data.get("geocodes") or []:
            if g.get("location"):
                return {"location": g["location"], "name": g.get("formatted_address") or address}
        return None

    extra = {"city": city} if city else {}
    try:
        got = _dig(_call_tool("maps_geo", {"address": address, **extra}))
        if got:
            return {"ok": True, **got}
    except Exception:
        pass   # MCP 主路挂了静默降级 REST
    try:
        resp = requests.get("https://restapi.amap.com/v3/geocode/geo",
                            params={"address": address, "key": AMAP_MAPS_API_KEY, **extra},
                            timeout=TIMEOUT)
        got = _dig(resp.json())
        if got:
            return {"ok": True, **got}
        return {"ok": False, "error": f"高德找不到「{address}」：试试具体楼栋名（如：安徽工业大学教三）"}
    except Exception as exc:
        return {"ok": False, "error": f"地理编码不可用：{str(exc)[:80]}"}

def route(origin: str, destination: str, mode: str = "walk") -> dict:
    # 坐标 → 坐标路线规划；统一归一化 {distance(米), duration(秒), steps[], polyline}
    bad = _check_key()
    if bad:
        return {"ok": False, "error": bad}
    mcp_tool, rest_url = MODE_TOOLS.get(mode, MODE_TOOLS["walk"])

    def _dig(data):
        paths = data.get("paths") or (data.get("data") or {}).get("paths") \
            or (data.get("route") or {}).get("paths")
        if not paths:
            return None
        p = paths[0]
        steps = [{"instruction": s.get("instruction") or "", "road": s.get("road") or "",
                  "distance": s.get("distance") or ""} for s in p.get("steps") or []]
        polyline = ";".join(filter(None, (s.get("polyline") or "" for s in p.get("steps") or [])))
        return {"distance": p.get("distance") or 0, "duration": p.get("duration") or 0,
                "steps": steps, "polyline": polyline}

    try:
        got = _dig(_call_tool(mcp_tool, {"origin": origin, "destination": destination}))
        if got:
            return {"ok": True, "provider": "mcp", **got}
    except Exception:
        pass
    try:
        resp = requests.get(rest_url, params={"origin": origin, "destination": destination,
                                              "key": AMAP_MAPS_API_KEY}, timeout=TIMEOUT)
        got = _dig(resp.json())
        if got:
            return {"ok": True, "provider": "rest", **got}
        return {"ok": False, "error": "路线规划没有返回方案（两点可能太近或超出支持范围）"}
    except Exception as exc:
        return {"ok": False, "error": f"路线规划不可用：{str(exc)[:80]}"}
