# 模型路由：候选池按优先级自动选择可用模型，配合后台滚动体检，全挂才降级演示
import time
from typing import List , Optional, Tuple

from AI import glm, ollama
from Backend.config import GLM_MODEL, GLM_MODEL_AGAIN, GLM_MODEL_BACKUP, OLLAMA_MODEL

# —— 候选池（顺序即优先级，.env 槽位决定；同名自动去重）——
def _dedup(items) -> List[str]:
    seen: List[str] = []
    for x in items:
        if x and x not in seen:
            seen.append(x)
    return seen

GLM_POOL = _dedup((GLM_MODEL, GLM_MODEL_AGAIN, GLM_MODEL_BACKUP))
OLLAMA_POOL = _dedup((OLLAMA_MODEL,))

# 复杂任务关键词：命中即走云端GLM（课表/作业/考试等准确性优先），否则走本地Ollama
COMPLEX_KEYWORDS = (
    "课表", "作业", "考试", "复习", "提醒", "日程", "计划",
    "成绩", "GPA", "学分", "导入", "安排", "复习表", "课程",
)

def _groups(utterance: str) -> List[Tuple[str, str]]:
    # 意图分组：复杂任务GLM池优先（池内按优先级），简单咨询本地优先，另一组整体后备
    # 第一版规则匹配意图，第二版可升级为LLM意图识别
    glm_list = [("glm", m) for m in GLM_POOL]
    ollama_list = [("ollama", m) for m in OLLAMA_POOL]
    if any(word in utterance for word in COMPLEX_KEYWORDS):
        return glm_list + ollama_list
    return ollama_list + glm_list

# —— 可用性探测：记录每个模型最近一次成败，失败进入冷却期，冷却期内优先跳过 ——
COOLDOWN_SECONDS = 60  # 失败冷却时长：期间直接试别的模型，到期自动重试（自愈）
_state: dict = {}      # {模型名: {"ok": 上次是否成功, "ts": 时间戳}}


def _mark(name: str, ok: bool) -> None:
    _state[name] = {"ok": ok, "ts": time.time()}


def _is_available(name: str) -> bool:
    s = _state.get(name)
    if s is None or s["ok"]:
        return True  # 从没试过或上次成功 → 可用
    return time.time() - s["ts"] >= COOLDOWN_SECONDS  # 冷却期内 → 暂不可用


def _order(candidates: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    # 排序：可用的按优先级排前，冷却中的垫底兜底（宁可多试，不直接放弃）
    return [c for c in candidates if _is_available(c[1])] + [c for c in candidates if not _is_available(c[1])]


def chat(messages: List[dict]) -> Tuple[Optional[str], Optional[str]]:
    # 返回 (回复正文, "提供方:模型名")；候选全挂时返回 (None, None)
    # 可用性感知 + 优先级：可用的强模型优先，冷却中的自动让位，体检/到期恢复后自动回归
    utterance = messages[-1]["content"] if messages else ""
    for provider, model in _order(_groups(utterance)):
        text = glm.chat(messages, model=model) if provider == "glm" else ollama.chat(messages, model=model)
        if text:
            _mark(model, True)
            return text, f"{provider}:{model}"
        _mark(model, False)
    return None, None


def probe_down() -> None:
    # 滚动体检：对"不可用/从未测过"的候选发极小探测请求，恢复即上线并打印
    for provider, model in [("glm", m) for m in GLM_POOL] + [("ollama", m) for m in OLLAMA_POOL]:
        if _state.get(model, {}).get("ok"):
            continue  # 在线模型不重复探测，省额度（真实流量会持续刷新它的状态）
        text = (glm.chat if provider == "glm" else ollama.chat)([{"role": "user", "content": "ping"}], model=model)
        _mark(model, bool(text))
        if text:
            print(f"[health] 模型 {model} 在线 ✓")


def status() -> dict:
    # 供 GET /health 展示实时模型状态
    out = {}
    for m in GLM_POOL + OLLAMA_POOL:
        s = _state.get(m)
        out[m] = {
            "ok": bool(s and s["ok"]),
            "checked_at": time.strftime("%H:%M:%S", time.localtime(s["ts"])) if s else None,
        }
    return out