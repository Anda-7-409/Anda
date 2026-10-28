
import re
import time
from html import unescape
from urllib.parse import quote, unquote

import requests

from Backend.config import ANY_SEARCH_KEY, QIANFAN_AI_SEARCH_KEY, SEARCH_COOLDOWN_SECONDS

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 8        
MAX_RESULTS = 5    

def _clean(fragment: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", fragment))).strip()

def _bing_search(query: str, max_results: int) -> dict:
    url = f"https://www.bing.com/search?q={quote(query)}&setlang=zh-hans&mkt=zh-CN"
    resp = requests.get(
        url,
        headers={"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    results = []
    for block in re.findall(r'<li class="b_algo".*?</li>', resp.text, re.S):
        head = re.search(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', block, re.S)
        if not head:
            continue
        link, title = head.group(1), _clean(head.group(2))
        if not title or not link.startswith("http"):
            continue
        tail = re.search(r"<p[^>]*>(.*?)</p>", block, re.S)
        results.append({"title": title, "url": link,
                        "snippet": _clean(tail.group(1)) if tail else ""})
        if len(results) >= max_results:
            break
    return {"ok": True, "provider": "bing", "query": query, "results": results}

def _ddg_search(query: str, max_results: int) -> dict:
    resp = requests.post("https://html.duckduckgo.com/html/", data={"q": query},
                         headers={"User-Agent": UA}, timeout=TIMEOUT)
    resp.raise_for_status()
    results = []
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.S)
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.S)
    for i, (href, title) in enumerate(links):
        m = re.search(r"uddg=([^&]+)", href)  
        url = unquote(m.group(1)) if m else href
        t = _clean(title)
        if not t or not url.startswith("http"):
            continue
        results.append({"title": t, "url": url,
                        "snippet": _clean(snips[i]) if i < len(snips) else ""})
        if len(results) >= max_results:
            break
    return {"ok": True, "provider": "duckduckgo", "query": query, "results": results}


def _qianfan_search(query: str, max_results: int) -> dict:
    resp = requests.post(
        "https://qianfan.baidubce.com/v2/ai_search/web_search",
        headers={"Authorization": f"Bearer {QIANFAN_AI_SEARCH_KEY}", "Content-Type": "application/json"},
        json={"messages": [{"role": "user", "content": query}]},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("references") or data.get("search_results") or []
    if isinstance(items, dict):
        items = items.get("value") or items.get("list") or []
    results = []
    for it in items[:max_results * 2]:
        url = it.get("url") or it.get("link") or ""
        if not url.startswith("http"):
            continue
        results.append({"title": it.get("title") or it.get("name") or url, "url": url,
                        "snippet": _clean(it.get("summary") or it.get("snippet") or it.get("content") or "")})
        if len(results) >= max_results:
            break
    return {"ok": True, "query": query, "results": results}


def _anysearch_search(query: str, max_results: int) -> dict:
    resp = requests.post(
        "https://api.anysearch.com/v1/search",
        headers={"Authorization": f"Bearer {ANY_SEARCH_KEY}", "Content-Type": "application/json"},
        json={"query": query, "max_results": min(max_results, 10),
              "zone": "cn", "language": "zh-CN"},
        timeout=TIMEOUT,
    )
    if resp.status_code == 402:
        raise RuntimeError("AnySearch 额度已耗尽")
    resp.raise_for_status()
    items = (resp.json().get("data") or {}).get("results") or []
    results = []
    for it in items[:max_results]:
        url = it.get("url") or ""
        if not url.startswith("http"):
            continue
        results.append({"title": it.get("title") or url, "url": url,
                        "snippet": _clean(it.get("snippet") or it.get("content") or "")})
    return {"ok": True, "query": query, "results": results}


COOLDOWN_SECONDS = SEARCH_COOLDOWN_SECONDS       
QUOTA_COOLDOWN_SECONDS = 3600                    
QUOTA_WORDS = ("额度", "余额", "欠费", "配额", "quota", "balance", "insufficient")
_state: dict = {}  


def _mark(name: str, ok: bool, quota: bool = False) -> None:
    _state[name] = {"ok": ok, "ts": time.time(),
                    "cooldown": QUOTA_COOLDOWN_SECONDS if (quota and not ok) else COOLDOWN_SECONDS}


def _is_available(name: str) -> bool:
    s = _state.get(name)
    if s is None or s["ok"]:
        return True  
    return time.time() - s["ts"] >= s.get("cooldown", COOLDOWN_SECONDS)


def _candidates():
    pool = []
    if QIANFAN_AI_SEARCH_KEY:
        pool.append(("qianfan", _qianfan_search))
    if ANY_SEARCH_KEY:
        pool.append(("anysearch", _anysearch_search))
    pool.append(("bing", _bing_search))
    pool.append(("duckduckgo", _ddg_search))
    return pool


def _order(candidates):
    return [c for c in candidates if _is_available(c[0])] + \
           [c for c in candidates if not _is_available(c[0])]


def search(query: str, max_results: int = MAX_RESULTS) -> dict:
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "搜索词不能为空"}
    errors = []
    empty = 0   
    for name, fn in _order(_candidates()):
        try:
            got = fn(query, max_results)
        except Exception as exc:
            text = str(exc)
            _mark(name, False, quota=any(w in text.lower() for w in QUOTA_WORDS))
            errors.append(f"{name}: {text[:80]}")
            continue
        _mark(name, True)
        if got["results"]:
            got["provider"] = name
            return got
        empty += 1
    if empty:
        return {"ok": False, "error": f"没搜到「{query}」的结果",
                "note": "搜索源可达但无结果，如实告知用户，不要编造链接"}
    return {"ok": False, "error": "；".join(errors) or "没有可用的搜索源",
            "note": "所有搜索源都不可用，如实告知用户稍后再试"}


def probe_down() -> None:
    for name, fn in _candidates():
        if _state.get(name, {}).get("ok"):
            continue  
        s = _state.get(name)
        if s and time.time() - s["ts"] < s.get("cooldown", COOLDOWN_SECONDS):
            continue  
        try:
            fn("ping", 1)
            _mark(name, True)
            print(f"[health] 搜索源 {name} 在线 ✓")
        except Exception as exc:
            text = str(exc)
            _mark(name, False, quota=any(w in text.lower() for w in QUOTA_WORDS))


def status() -> dict:
    out = {}
    for name, _ in _candidates():
        s = _state.get(name)
        out[name] = {
            "ok": bool(s and s["ok"]),
            "checked_at": time.strftime("%H:%M:%S", time.localtime(s["ts"])) if s else None,
        }
    return out

_TRIGGER = ("全网搜索", "帮我搜一下", "帮我搜", "全网搜", "上网搜", "搜一下", "网上查", "上网查", "查一下",
            "搜下", "搜索", "查查")   

def search_tool(utterance: str, user_id: int, **_) -> dict:
    q = utterance or ""
    for w in sorted(_TRIGGER, key=len, reverse=True):   
        q = q.replace(w, " ")
    q = " ".join(q.split()).strip(" ，。！？!?、")
    q = re.sub(r"^(一下|啊|呃|那个|嗯|帮我|我要|想)+", "", q).strip()   
    if not q:
        return {"ok": False, "error": "没听懂要搜什么", "hint": "追问用户具体想搜的内容"}
    got = search(q)
    if not got["ok"]:
        return {"ok": False, "error": got["error"], "hint": got.get("note", "")}
    if not got["results"]:
        return {"ok": False, "error": f"没搜到「{q}」的结果", "hint": got.get("note", "")}
    return {"query": q, "count": len(got["results"]), "provider": got["provider"],
            "results": got["results"], "note": "必须基于以上真实结果作答，引用结论时带上来源标题；没有的结果不许编"}
