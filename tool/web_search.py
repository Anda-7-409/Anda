
# tool/web_search.py (全网搜索工具链) Agent 可调用的联网搜索：多源 AI Search 路由
# 候选池：百度千帆「百度搜索」→ AnySearch → Bing抓取 → DDG（按优先级，未配 Key 的源自动跳过）
# 自愈路由：源失败进冷却自动换下一个，后台滚动体检恢复即回归；额度耗尽进长冷却
import re
import time
from html import unescape
from urllib.parse import quote, unquote

import requests

from Backend.config import ANY_SEARCH_KEY, QIANFAN_AI_SEARCH_KEY, SEARCH_COOLDOWN_SECONDS

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
TIMEOUT = 8        # 秒：搜索是同步工具，超时必须短，别拖垮整条对话链
MAX_RESULTS = 5    # 结果条数上限：既够 AI 交叉比对，又不撑爆提示词

def _clean(fragment: str) -> str:
    # 去 HTML 标签 → 实体反转义 → 压缩空白
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
    # 备用搜索源：DuckDuckGo HTML 版（也免 Key）；主源挂掉或零结果时兕一层
    resp = requests.post("https://html.duckduckgo.com/html/", data={"q": query},
                         headers={"User-Agent": UA}, timeout=TIMEOUT)
    resp.raise_for_status()
    results = []
    links = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', resp.text, re.S)
    snips = re.findall(r'class="result__snippet"[^>]*>(.*?)</a>', resp.text, re.S)
    for i, (href, title) in enumerate(links):
        m = re.search(r"uddg=([^&]+)", href)   # DDG 外链先经 /l/?uddg= 包一层，需解开真实地址
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
    # 百度千帆 ai_search（REST 直连，与其 MCP ai_search 工具同一能力；.env: QIANFAN_AI_SEARCH_KEY）
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
    # AnySearch（AI 搜索基础设施；.env: ANY_SEARCH_KEY，402=额度耗尽进长冷却）
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


# —— 多源路由：与 model_router 同一套范式（候选池 + 失败冷却 + 滚动体检恢复）——
COOLDOWN_SECONDS = SEARCH_COOLDOWN_SECONDS       # 普通失败（网络/5xx）冷却时长
QUOTA_COOLDOWN_SECONDS = 3600                    # 额度耗尽类错误冷却 1 小时，避免每分钟白烧请求
QUOTA_WORDS = ("额度", "余额", "欠费", "配额", "quota", "balance", "insufficient")
_state: dict = {}   # {源名: {"ok": 上次是否成功, "ts": 时间戳, "cooldown": 本次冷却时长}}


def _mark(name: str, ok: bool, quota: bool = False) -> None:
    _state[name] = {"ok": ok, "ts": time.time(),
                    "cooldown": QUOTA_COOLDOWN_SECONDS if (quota and not ok) else COOLDOWN_SECONDS}


def _is_available(name: str) -> bool:
    s = _state.get(name)
    if s is None or s["ok"]:
        return True  # 从没试过或上次成功 → 可用
    return time.time() - s["ts"] >= s.get("cooldown", COOLDOWN_SECONDS)


def _candidates():
    # 候选池（顺序即优先级）：配了 Key 的 API 源在前，零 Key 抓取源永远垫底兜底
    pool = []
    if QIANFAN_AI_SEARCH_KEY:
        pool.append(("qianfan", _qianfan_search))
    if ANY_SEARCH_KEY:
        pool.append(("anysearch", _anysearch_search))
    pool.append(("bing", _bing_search))
    pool.append(("duckduckgo", _ddg_search))
    return pool


def _order(candidates):
    # 可用的按优先级排前，冷却中的垫底兜底（宁可多试，不直接放弃）
    return [c for c in candidates if _is_available(c[0])] + \
           [c for c in candidates if not _is_available(c[0])]


def search(query: str, max_results: int = MAX_RESULTS) -> dict:
    # 统一入口（多源路由）：按优先级逐个尝试，某源挂掉/冷却中自动换下一个；全挂才返回结构化错误
    query = (query or "").strip()
    if not query:
        return {"ok": False, "error": "搜索词不能为空"}
    errors = []
    empty = 0   # 可达但零结果的源单独计数：能连上≠没搜到
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
    # 滚动体检：只重测“不在冷却期的不可用/未测过”源，发极小探测请求，恢复即上线
    for name, fn in _candidates():
        if _state.get(name, {}).get("ok"):
            continue  # 在线源不重复探测，省额度
        s = _state.get(name)
        if s and time.time() - s["ts"] < s.get("cooldown", COOLDOWN_SECONDS):
            continue  # 仍在冷却期内（尤其额度长冷却）不重复烧请求
        try:
            fn("ping", 1)
            _mark(name, True)
            print(f"[health] 搜索源 {name} 在线 ✓")
        except Exception as exc:
            text = str(exc)
            _mark(name, False, quota=any(w in text.lower() for w in QUOTA_WORDS))


def status() -> dict:
    # 供 GET /health 展示实时搜索源状态
    out = {}
    for name, _ in _candidates():
        s = _state.get(name)
        out[name] = {
            "ok": bool(s and s["ok"]),
            "checked_at": time.strftime("%H:%M:%S", time.localtime(s["ts"])) if s else None,
        }
    return out

_TRIGGER = ("全网搜索", "帮我搜一下", "帮我搜", "全网搜", "上网搜", "搜一下", "网上查", "上网查", "查一下",
            "搜下", "搜索", "查查")   # 长词在前，避免"帮我搜"先把"搜一下"切碎留下"一下"

def search_tool(utterance: str, user_id: int) -> dict:
    # Agent 工具入口：orchestrator 以 fn(utterance=, user_id=) 调用
    # 职责：剥掉触发词得到真正的搜索词 → 调 search() → 返回结构化结果供 orchestrator 注入提示词
    q = utterance or ""
    for w in sorted(_TRIGGER, key=len, reverse=True):   # 运行时再按长度降序兑一次底，防后续手改元组顺序又踩坑
        q = q.replace(w, " ")
    q = " ".join(q.split()).strip(" ，。！？!?、")
    q = re.sub(r"^(一下|啊|呃|那个|嗯|帮我|我要|想)+", "", q).strip()   # 清掉删完触发词残留的口语填充词
    if not q:
        return {"ok": False, "error": "没听懂要搜什么", "hint": "追问用户具体想搜的内容"}
    got = search(q)
    if not got["ok"]:
        return {"ok": False, "error": got["error"], "hint": got.get("note", "")}
    if not got["results"]:
        return {"ok": False, "error": f"没搜到「{q}」的结果", "hint": got.get("note", "")}
    return {"query": q, "count": len(got["results"]), "provider": got["provider"],
            "results": got["results"], "note": "必须基于以上真实结果作答，引用结论时带上来源标题；没有的结果不许编"}
