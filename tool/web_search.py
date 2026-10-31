# web_search.py — 联网搜索：qianfan → anysearch → ddg 三级聚合 + 冷却降级
# 契约（docs/refactoring.md 3.2；消费方：/health 与 orchestrator.TOOLS["web_search"]）：
#   search_tool(utterance, user_id, refs) -> {"ok","query","results":[{title,url,snippet}]} | {"ok":False,"error"}
#   search(query, max_results) -> list          # 聚合入口：按源顺序取第一个成功者
#   probe_down(source)                          # 把某源标记进冷却（冷却期内跳过）
#   status() -> {"ok": bool, "sources": [str]}  # /health 透传给前端
import json
import logging
import re
import time

import requests

from Backend import config

log = logging.getLogger("anda.web_search")
_TIMEOUT = 15
_cooldown = {}   # source -> 进入冷却的时间戳

def probe_down(source: str) -> None:
    # 某源调用失败时标记冷却；冷却期内 search() 跳过它，避免每轮都撞死源
    _cooldown[source] = time.time()

def _in_cooldown(source: str) -> bool:
    t = _cooldown.get(source)
    if t is None:
        return False
    if time.time() - t >= config.SEARCH_COOLDOWN_SECONDS:
        _cooldown.pop(source, None)   # 冷却结束，重新参与轮询
        return False
    return True

def _qianfan(query: str, max_results: int) -> list:
    # 百度千帆 AI 搜索：bce-v3 Key，Bearer 鉴权，返回 references 列表
    if not config.QIANFAN_AI_SEARCH_KEY:
        raise RuntimeError("未配置 QIANFAN_AI_SEARCH_KEY")
    r = requests.post(
        "https://qianfan.baidubce.com/v2/ai_search",
        headers={"Authorization": f"Bearer {config.QIANFAN_AI_SEARCH_KEY}",
                 "Content-Type": "application/json"},
        json={"messages": [{"content": query, "role": "user"}],
              "search_source": "baidu_search_v2", "resource_type": "web"},
        timeout=_TIMEOUT)
    r.raise_for_status()
    refs = r.json().get("references") or []
    return [{"title": x.get("title", ""), "url": x.get("url") or x.get("web_anchor", ""),
             "snippet": (x.get("content") or "")[:300]} for x in refs[:max_results]]

def _anysearch(query: str, max_results: int) -> list:
    # AnySearch（api.anysearch.com）：MCP Streamable HTTP 端点，JSON-RPC tools/call
    # 若服务端工具名/参数有出入只影响这一级，search() 会自动降级，不影响主链路
    if not config.ANY_SEARCH_KEY:
        raise RuntimeError("未配置 ANY_SEARCH_KEY")
    r = requests.post(
        "https://api.anysearch.com/mcp",
        headers={"Authorization": f"Bearer {config.ANY_SEARCH_KEY}",
                 "Accept": "application/json, text/event-stream"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "web_search", "arguments": {"query": query, "limit": max_results}}},
        timeout=_TIMEOUT)
    r.raise_for_status()
    body = r.text
    if "text/event-stream" in r.headers.get("Content-Type", ""):   # SSE 帧：抽出 data: 行
        body = "".join(ln[5:].strip() for ln in body.splitlines() if ln.startswith("data:"))
    data = json.loads(body)
    content = (data.get("result") or {}).get("content") or []
    text = " ".join(c.get("text", "") for c in content if isinstance(c, dict)).strip()
    if not text:
        raise RuntimeError(f"anysearch 空结果：{data.get('error') or '未知错误'}")
    items = [{"title": m.group(1).strip(), "url": m.group(2), "snippet": ""}
             for m in re.finditer(r"\[([^\]\n]+)\]\s*\((https?://[^)\s]+)\)", text)]
    if not items:   # 没解析出链接时整体作为摘要返回，模型仍可据此作答
        items = [{"title": query, "url": "", "snippet": text[:300]}]
    return items[:max_results]

def _ddg(query: str, max_results: int) -> list:
    # 可选第三级：安装 duckduckgo_search 后自动启用，未安装则该源恒跳过
    from duckduckgo_search import DDGS
    with DDGS() as d:
        return [{"title": x.get("title", ""), "url": x.get("href", ""),
                 "snippet": x.get("body", "")} for x in d.text(query, max_results=max_results)]

_SOURCES = (("qianfan", _qianfan), ("anysearch", _anysearch), ("ddg", _ddg))

def search(query, max_results=5) -> list:
    query = (query or "").strip()
    if not query:
        return []
    for name, fn in _SOURCES:
        if _in_cooldown(name):
            continue
        try:
            items = fn(query, max_results)
            if items:
                return items
        except Exception as e:
            log.warning("search source %s failed: %s", name, e)
            probe_down(name)
    return []

def status() -> dict:
    return {"ok": bool(config.QIANFAN_AI_SEARCH_KEY or config.ANY_SEARCH_KEY),
            "sources": [name for name, _ in _SOURCES if not _in_cooldown(name)]}

def search_tool(utterance="", user_id=None, refs=None, **_) -> dict:
    q = (utterance or "").strip()
    if not q:
        return {"ok": False, "error": "没有可搜索的内容"}
    results = search(q, 5)
    if not results:
        return {"ok": False, "error": "搜索服务暂时都不可用，请稍后再试"}
    return {"ok": True, "query": q, "result_count": len(results), "results": results}
