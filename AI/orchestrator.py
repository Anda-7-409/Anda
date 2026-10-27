import json
import secrets
from typing import List, Optional

from AI import model_router
from AI.prompt import prompt as prompt_mod


TOOLS: dict = {}

DEMO_REPLY = (
    "（演示模式）我暂时还没连上大脑呢~ GLM_API_KEY 未配置、本地 Ollama 也未能启动成功呀~\n"
    "接上任意一个我就能正常回答啦：\n"
    "1. 云端：.env 里填 GLM_API_KEY（智谱开放平台申请）\n"
    "2. 本地：安装 Ollama 后执行 ollama pull 模型名称（如 qwen2.5）\n"
)

def _plan_tools(utterance: str) -> List[str]:
    hits = []
    for name, meta in TOOLS.items():
        if not any(k in utterance for k in meta.get("keywords", [])):
            continue
        if any(e in utterance for e in meta.get("exclude", ())):
            continue
        hits.append(name)
    return hits

def run(user_id: int, utterance: str, context: Optional[List[dict]] = None, ref_block: str = "") -> dict:
    tool_names = _plan_tools(utterance)

    tool_calls, actions = [], []
    for name in tool_names:
        try:
            result = TOOLS[name]["fn"](utterance=utterance, user_id=user_id, refs=refs or [])
            status = "success"
        except Exception as exc:
            result = {"error": str(exc)}
            status = "failed"
        tool_calls.append({"tool_name": name, "status": status, "result": result})
        actions.append(f"调用工具 {name}")

    ask = utterance
    if ref_block:
        ask = f"{ask}\n\n{ref_block}"   
    if tool_calls:
        block = "\n".join(
            f"- {c['tool_name']}: {json.dumps(c['result'], ensure_ascii=False)}" for c in tool_calls
        )
        ask = f"{utterance}\n\n【工具执行结果】\n{block}\n请基于以上工具结果作答，不要编造数据。"
    messages = prompt_mod.build_messages(ask, context)
    answer, provider = model_router.chat(messages)
    if not answer:
        answer = DEMO_REPLY

    return {
        "id": secrets.token_hex(6),  
        "answer": answer,
        "tool_calls": tool_calls,
        "actions_taken": actions,
        "needs_confirm": False,      
        "confirm_payload": None,
        "provider": provider or "demo",
    }
