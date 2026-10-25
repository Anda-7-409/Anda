#  (任务协调器) Agent流水线：意图识别 → 任务拆解 → 工具调用 → 结果汇总（plan.md 技术创新核心）
import json
import secrets
from typing import List, Optional

from AI import model_router
from AI.prompt import prompt as prompt_mod

# 工具注册表：{工具名: {"keywords": 触发关键词, "exclude": 命中即排除词(可选), "fn": 可调用函数}}
# 后续 skill/（课表查询、GPA计算、复习计划…）与 MCP/（高德地图、天气…）落地后逐个注册进来
TOOLS: dict = {}

DEMO_REPLY = (
    "（演示模式）我暂时还没连上大脑呢~ GLM_API_KEY 未配置、本地 Ollama 也未能启动成功呀~\n"
    "接上任意一个我就能正常回答啦：\n"
    "1. 云端：.env 里填 GLM_API_KEY（智谱开放平台申请）\n"
    "2. 本地：安装 Ollama 后执行 ollama pull 模型名称（如 qwen2.5）\n"
)

def _plan_tools(utterance: str) -> List[str]:
    # 任务拆解：命中 keywords 且未命中 exclude 才触发（第一版规则匹配，第二版可升级为LLM拆解）
    # exclude 让关键词可以放宽：例“我有什么提醒”含“提醒”会命中设提醒，但“有什么”把它挡下，只走查提醒
    hits = []
    for name, meta in TOOLS.items():
        if not any(k in utterance for k in meta.get("keywords", [])):
            continue
        if any(e in utterance for e in meta.get("exclude", ())):
            continue
        hits.append(name)
    return hits

def run(user_id: int, utterance: str, context: Optional[List[dict]] = None, ref_block: str = "") -> dict:
    # ① 意图识别 + 任务拆解（只看用户原话；ref_block 单独传，不参与匹配，防止引用文本里的词误触发工具）
    tool_names = _plan_tools(utterance)

    # ② 工具调用（工具结果注入提示词由下一版拼接，TODO）
    tool_calls, actions = [], []
    for name in tool_names:
        try:
            result = TOOLS[name]["fn"](utterance=utterance, user_id=user_id)
            status = "success"
        except Exception as exc:
            result = {"error": str(exc)}
            status = "failed"
        tool_calls.append({"tool_name": name, "status": status, "result": result})
        actions.append(f"调用工具 {name}")

    # ③ 结果汇总 → 生成自然语言答案（三级降级：主模型 → 备用模型 → 演示回复）
    # 工具结果拼进本轮问题，让模型基于真实数据回答（原TODO：升级为结构化 tool 消息注入）
    ask = utterance
    if ref_block:
        ask = f"{ask}\n\n{ref_block}"   # 引用文件内容只给模型看，不给关键词匹配看
    if tool_calls:
        block = "\n".join(
            f"- {c['tool_name']}: {json.dumps(c['result'], ensure_ascii=False)}" for c in tool_calls
        )
        ask = f"{utterance}\n\n【工具执行结果】\n{block}\n请基于以上工具结果作答，不要编造数据。"
    messages = prompt_mod.build_messages(ask, context)
    answer, provider = model_router.chat(messages)
    if not answer:
        answer = DEMO_REPLY

    # ④ 组装返回（字段契约：plan.md /agent/chat + 前端 agent_ai.html）
    return {
        "id": secrets.token_hex(6),  # 任务ID，task表落地后改为落库自增ID
        "answer": answer,
        "tool_calls": tool_calls,
        "actions_taken": actions,
        "needs_confirm": False,       # TODO：危险操作确认机制（接 /agent/confirm）
        "confirm_payload": None,
        "provider": provider or "demo",
    }