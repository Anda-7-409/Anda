import time
from typing import List , Optional, Tuple

from AI import glm, ollama
from Backend.config import GLM_MODEL, GLM_MODEL_AGAIN, GLM_MODEL_BACKUP, OLLAMA_MODEL

def _dedup(items) -> List[str]:
    seen: List[str] = []
    for x in items:
        if x and x not in seen:
            seen.append(x)
    return seen

GLM_POOL = _dedup((GLM_MODEL, GLM_MODEL_AGAIN, GLM_MODEL_BACKUP))
OLLAMA_POOL = _dedup((OLLAMA_MODEL,))

COMPLEX_KEYWORDS = (
    "课表", "作业", "考试", "复习", "提醒", "日程", "计划",
    "成绩", "GPA", "学分", "导入", "安排", "复习表", "课程",
)

def _groups(utterance: str) -> List[Tuple[str, str]]:
    glm_list = [("glm", m) for m in GLM_POOL]
    ollama_list = [("ollama", m) for m in OLLAMA_POOL]
    if any(word in utterance for word in COMPLEX_KEYWORDS):
        return glm_list + ollama_list
    return ollama_list + glm_list

COOLDOWN_SECONDS = 60  
_state: dict = {}      


def _mark(name: str, ok: bool) -> None:
    _state[name] = {"ok": ok, "ts": time.time()}


def _is_available(name: str) -> bool:
    s = _state.get(name)
    if s is None or s["ok"]:
        return True  
    return time.time() - s["ts"] >= COOLDOWN_SECONDS  


def _order(candidates: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    return [c for c in candidates if _is_available(c[1])] + [c for c in candidates if not _is_available(c[1])]


def chat(messages: List[dict]) -> Tuple[Optional[str], Optional[str]]:
    utterance = messages[-1]["content"] if messages else ""
    for provider, model in _order(_groups(utterance)):
        text = glm.chat(messages, model=model) if provider == "glm" else ollama.chat(messages, model=model)
        if text:
            _mark(model, True)
            return text, f"{provider}:{model}"
        _mark(model, False)
    return None, None


def chat_with_tools(messages: List[dict], tools: List[dict]) -> Tuple[Optional[dict], Optional[str]]:
    """混合策略：function calling 只走 GLM 池（本地 Ollama 的 FC 输出不稳），
    由编排器在 GLM 全挂时回落到关键词兜底路径。"""
    for provider, model in _order([("glm", m) for m in GLM_POOL]):
        msg = glm.chat_with_tools(messages, tools, model=model)
        if msg:
            _mark(model, True)
            return msg, f"{provider}:{model}"
        _mark(model, False)
    return None, None


def chat_text(messages: List[dict]) -> Tuple[Optional[str], Optional[str]]:
    """工具内部生成类调用（如代码生成）：只走 GLM 池带故障转移，不落 Ollama。"""
    for provider, model in _order([("glm", m) for m in GLM_POOL]):
        text = glm.chat(messages, model=model)
        if text:
            _mark(model, True)
            return text, f"{provider}:{model}"
        _mark(model, False)
    return None, None


def probe_down() -> None:
    for provider, model in [("glm", m) for m in GLM_POOL] + [("ollama", m) for m in OLLAMA_POOL]:
        if _state.get(model, {}).get("ok"):
            continue 
        text = (glm.chat if provider == "glm" else ollama.chat)([{"role": "user", "content": "ping"}], model=model)
        _mark(model, bool(text))
        if text:
            print(f"[health] 模型 {model} 在线 ✓")


def status() -> dict:
    out = {}
    for m in GLM_POOL + OLLAMA_POOL:
        s = _state.get(m)
        out[m] = {
            "ok": bool(s and s["ok"]),
            "checked_at": time.strftime("%H:%M:%S", time.localtime(s["ts"])) if s else None,
        }
    return out
