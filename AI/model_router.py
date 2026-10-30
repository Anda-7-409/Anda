# AI/model_router.py — 权重降序逐个试,全灭477。无默认态/无显式路由/无冷却。
import json, os, logging
from pathlib import Path
import httpx

log = logging.getLogger("anda.router")
AI_DIR = Path(__file__).parent

_MODELS = {m["model_id"]: m for m in json.loads(
    (AI_DIR / "models.json").read_text("utf-8"))["models"]}

def _chain(ability: str) -> list[str]:
    """权重降序,过滤:幽灵id/权重≤0/缺key(无key模型天然出局)。"""
    ids = [m["model_id"] for m in sorted(
        _MODELS.values(), key=lambda m: -m["ability_weights"].get(ability, 0))]
    return [mid for mid in ids
            if (m := _MODELS[mid])["ability_weights"].get(ability, 0) > 0
            and (not m.get("api_key_env") or os.getenv(m["api_key_env"]))]

def chat(ability: str, messages: list, tools=None):
    """→ (text, provider) 或 抛 NoModelError(由路由层转477)。链上每个吃满各自timeout。"""
    for mid in _chain(ability):
        m = _MODELS[mid]
        headers = {"Authorization": f"Bearer {os.environ[m['api_key_env']]}"
                   } if m.get("api_key_env") else {}
        try:
            payload = {k: v for k, v in {"messages": messages, "tools": tools}.items() if v}
            r = httpx.post(m["endpoint"], headers=headers,
                           json={**payload, "model": m["model_name"]},
                           timeout=m.get("timeout", 30))
            r.raise_for_status()
            text = (r.json()["choices"][0]["message"].get("content") or "").strip()
            if text:                       # 空/None文本视为该模型失败,继续下一个
                return text, f"{m.get('provider', 'unknown')}:{mid}"
        except Exception as e:
            log.warning("model %s failed: %s", mid, e)
    raise NoModelError(ability)

class NoModelError(Exception): pass

# ---------- FastAPI 路由层 ----------
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
app = FastAPI()

@app.post("/ai/chat")
def ai_chat(req: Request):
    ability, messages = req.query_params.get("ability", "chat"), None
    # 实际从body取——示意,按你的请求模型替换
    return JSONResponse(status_code=477, content={
        "code": 477, "msg": "无可用模型,已切换演示模式",
        "demo": True}) if not (msgs := _body(req).get("messages")) else _try_chat(req)

def _try_chat(req):
    from fastapi.responses import JSONResponse
    try:
        text, provider = chat(req_ability, req_msgs, req_tools)
        return {"text": text, "provider": provider}
    except NoModelError:
        return JSONResponse(status_code=示意477, content={...})
