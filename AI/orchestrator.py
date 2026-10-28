
import json
import secrets
from typing import List, Optional

from AI import model_router
from AI.prompt import prompt as prompt_mod

TOOLS: dict = {}

MAX_FC_ROUNDS = 2          
MAX_CALLS_PER_ROUND = 4    

DEMO_REPLY = "（演示模式：当前没有可用的模型服务）"


def _plan_tools(utterance: str) -> List[str]:
    # 离线识别用户意图，确保服务全程可用
    names = []
    for name, meta in TOOLS.items():
        words = meta.get("keywords", ())
        exclude = meta.get("exclude", ())
        if any(k in utterance for k in words) and not any(x in utterance for x in exclude):
            names.append(name)
    return names


def _tool_schemas() -> List[dict]:
    """从注册表生成 OpenAI function calling 格式的工具表（最小版：每个工具只有 task 一个参数）。"""
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": meta.get("desc", ""),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "task": {
                            "type": "string",
                            "description": "交给该工具的任务，用一句完整中文描述，包含关键细节（如时间、文件名）",
                        }
                    },
                    "required": ["task"],
                },
            },
        }
        for name, meta in TOOLS.items()
    ]


def _exec_tool(name: str, task: str, user_id: int, refs: Optional[list]) -> dict:
    meta = TOOLS.get(name)
    if not meta:
        return {"tool_name": name, "status": "failed", "result": {"error": f"未知工具 {name}"}}
    try:
        result = meta["fn"](utterance=task, user_id=user_id, refs=refs or [])
        status = "success"
    except Exception as exc:
        result, status = {"error": str(exc)}, "failed"
    return {"tool_name": name, "status": status, "result": result}


def _fc_pipeline(messages: List[dict], schemas: List[dict], user_id: int,
                 refs: Optional[list], fallback_task: str):
    """GLM function calling 主路径。
    返回 (answer, provider, tool_calls_log)；answer 为 None 表示 GLM 不可用，需走关键词兜底。"""
    log: List[dict] = []
    provider = None
    for _ in range(MAX_FC_ROUNDS):
        msg, provider = model_router.chat_with_tools(messages, schemas)
        if msg is None:
            return None, provider, log
        calls = msg.get("tool_calls") or []
        if not calls:
            return msg.get("content") or None, provider, log
        messages = messages + [msg]
        for c in calls[:MAX_CALLS_PER_ROUND]:
            fn = c.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
                if not isinstance(args, dict):
                    args = {}
            except Exception:
                args = {}
            rec = _exec_tool(fn.get("name", ""), args.get("task") or fallback_task, user_id, refs)
            log.append(rec)
            messages.append({
                "role": "tool",
                "tool_call_id": c.get("id") or fn.get("name", ""),
                "content": json.dumps(rec["result"], ensure_ascii=False),
            })

    msg, provider = model_router.chat_with_tools(messages, [])
    if msg:
        return msg.get("content") or None, provider, log
    return None, provider, log


def run(user_id: int, utterance: str, context=None, ref_block: str = "", refs=None) -> dict:
    action_id = secrets.token_hex(4)


    messages = prompt_mod.build_messages(utterance, context)
    if ref_block:
        messages[-1]["content"] = f"{messages[-1]['content']}\n\n{ref_block}"
    answer, provider, tool_calls = _fc_pipeline(messages, _tool_schemas(), user_id, refs, utterance)

 
    if answer is None:
        tool_calls = []
        for name in _plan_tools(utterance):
            tool_calls.append(_exec_tool(name, utterance, user_id, refs))
        ask = utterance
        if ref_block:
            ask = f"{ask}\n\n{ref_block}"
        if tool_calls:
            block = "\n".join(
                f"- {c['tool_name']}: {json.dumps(c['result'], ensure_ascii=False)}"
                for c in tool_calls
            )
            ask = f"{ask}\n\n【工具执行结果】\n{block}\n请基于以上工具结果作答，不要编造数据。"
        answer, provider = model_router.chat(prompt_mod.build_messages(ask, context))
        if answer is None:
            answer = DEMO_REPLY

    return {
        "answer": answer,
        "tool_calls": [
            {"tool_name": c["tool_name"], "status": c["status"], "result": c["result"]}
            for c in tool_calls
        ],
        "actions_taken": [f"调用工具 {c['tool_name']}（{c['status']}）" for c in tool_calls],
        "needs_confirm": False,
        "action_id": action_id,
        "provider": provider,
    }
