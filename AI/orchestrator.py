import json, secrets, logging
from AI import model_router
log = logging.getLogger("anda.orchestrator")
TOOLS = {}

_DEMO = "演示模式：AI服务出现故障,但这不影响我们继续，对吧？"
_MAX_ROUNDS = 2   # function calling 最多轮数（契约 2.3：单轮≤4次工具调用，最多2轮）
_MAX_CALLS = 4
_SYS_FC = ("你是校园AI助手安答。规则："
           "1) 凡是能用提供的工具完成的请求，必须实际调用工具，绝不只用文字承诺；"
           "2) 工具结果里带有链接（image_url/download_url）或文件名时，必须在回答中原样给出，方便用户点击。")

def _match(utterance: str):
    # 离线兜底：关键词匹配选工具（FC 不可用时才走这条路）
    hit = []
    for name, cfg in TOOLS.items():
        if any(k in utterance for k in cfg.get("exclude", [])):
            continue
        if any(k in utterance for k in cfg.get("keywords", [])):
            hit.append(name)
    return hit

_PROMISE_WORDS = ("我来", "让我来", "我帮你", "为你生成", "为你画", "为你写",
                  "正在为你", "马上为你", "这就为你")

def _is_promise(answer: str) -> bool:
    # 模型口头承诺要执行却没调工具（FC 抖动）：有承诺词且没有给出任何真实链接/结果
    a = (answer or "").strip()
    return bool(a) and any(w in a for w in _PROMISE_WORDS) and "http" not in a

def _fc_tools():
    # TOOLS 注册表 → OpenAI function calling 工具规格；desc 来自 agent_service 注册内容
    return [{"type": "function", "function": {
                "name": name, "description": cfg.get("desc", ""),
                "parameters": {"type": "object", "properties": {
                    "task": {"type": "string", "description":
                             "要执行的任务描述，需包含所有必要细节（课程名/时间/地点/查询内容等）"}},
                    "required": ["task"]}}}
            for name, cfg in TOOLS.items()]

def _exec(call: dict, utterance: str, user_id: int, refs) -> dict:
    # 执行一次工具调用（FC 与关键词兜底共用）；模型提炼的 task 优先于用户原话，失败不抛出（ok 字段防幻觉）
    name = (call.get("name") or "").strip()
    try:
        args = json.loads(call.get("arguments") or "{}")
        if not isinstance(args, dict):
            args = {}
    except Exception:
        args = {}
    task = (args.get("task") or args.get("utterance") or "").strip() or utterance
    cfg = TOOLS.get(name)
    if not cfg:
        return {"tool_name": name or "unknown", "status": "fail",
                "result": {"ok": False, "error": "未注册的工具"}}
    try:
        result = cfg["fn"](utterance=task, user_id=user_id, refs=list(refs or []))
    except Exception as e:
        log.warning("tool %s failed: %s", name, e)
        result = {"ok": False, "code": 51, "message": f"工具执行异常：{e}"}
    return {"tool_name": name, "status": "ok" if result.get("ok") else "fail", "result": result}

def _normalize(ctx):
    # 记忆窗口里的 role 是 "user"/"ai"，OpenAI 兼容接口只认 assistant
    return [{"role": "assistant" if m.get("role") == "ai" else m.get("role", "user"),
             "content": m.get("content", "")} for m in (ctx or [])]

def run(user_id, utterance, ctx=None, ref_block="", refs=None):
    user_msg = f"{ref_block}\n\n{utterance}" if ref_block else utterance
    messages = [*_normalize(ctx), {"role": "user", "content": user_msg}]
    messages.insert(0, {"role": "system", "content": _SYS_FC})
    tool_calls, answer, provider = [], "", ""

    # 主路径：function calling——模型自动识别要调的工具，结果回填后可继续调用（多轮）
    for _round in range(_MAX_ROUNDS):
        try:
            msg, provider = model_router.chat("tool_use", messages, tools=_fc_tools())
        except Exception as e:
            log.warning("fc round %s failed: %s", _round, e)
            break
        tc_list = (msg.get("tool_calls") or [])[:_MAX_CALLS]
        if not tc_list:
            answer = (msg.get("content") or "").strip()
            break
        calls = [{"id": tc.get("id", ""), "name": (tc.get("function") or {}).get("name", ""),
                  "arguments": (tc.get("function") or {}).get("arguments")} for tc in tc_list]
        executed = [_exec(c, utterance, user_id, refs) for c in calls]
        tool_calls.extend(executed)
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tc_list})
        messages.extend({"role": "tool", "tool_call_id": c["id"],
                         "content": json.dumps(e["result"], ensure_ascii=False)}
                        for c, e in zip(calls, executed))

    # 无回答，或 FC 只口头承诺没执行（关键词命中时）→ 走兜底补工具结果
    if not answer or (not tool_calls and _is_promise(answer) and _match(utterance)):
        if tool_calls:
            # FC 已执行过工具但轮数用尽还没有回答：让模型基于工具结果做最终总结
            # （否则消息以 role:"tool" 结尾，无工具表的 general 调用会模仿出 <tool_call> 文本）
            messages.append({"role": "user",
                             "content": "请根据以上工具执行结果，用中文自然语言回答用户的问题；不要再调用工具。"})
        else:   # FC 不可用/未执行才走关键词兜底；已执行过工具就不重复执行（防重复写库）
            for name in _match(utterance)[:_MAX_CALLS]:
                tool_calls.append(_exec({"name": name, "arguments": "{}"}, utterance, user_id, refs))
            if tool_calls:
                block = "\n".join(f"[{t['tool_name']}] {t['result']}" for t in tool_calls)
                messages.append({"role": "user",
                                 "content": f"工具执行结果：\n{block}\n\n用户问题：{utterance}"})
        try:
            msg, provider = model_router.chat("general", messages)
            answer = (msg or {}).get("content") or ""
        except Exception as e:
            log.warning("模型调用失败#:#: %s", e)

    if not answer:   # 全部在线模型挂了：最后试本地离线模型（mimo9b，断网/断API也能答）
        try:
            msg, provider = model_router.chat("offline", messages)
            answer = (msg or {}).get("content") or ""
        except Exception as e:
            log.warning("offline model failed: %s", e)

    if not answer:
        answer, provider = _DEMO, "demo"

    return{
        "answer": answer,
        "tool_calls": tool_calls,
        "actions_taken": [t["tool_name"] for t in tool_calls if t["status"] == "ok"],
        "needs_confirm": False,
        "action_id": secrets.token_hex(4),
        "provider": provider,
    }

def run_stream(user_id, utterance, ctx=None, ref_block="", refs=None):
    # 流式版：主路径 FC 多轮（模型自动选工具，事件照常流式），不可用时退回关键词匹配兜底
    user_msg = f"{ref_block}\n\n{utterance}" if ref_block else utterance
    messages = [*_normalize(ctx), {"role": "user", "content": user_msg}]
    messages.insert(0, {"role": "system", "content": _SYS_FC})
    tool_calls, answer, provider = [], "", ""

    for _round in range(_MAX_ROUNDS):
        calls = []
        try:
            for ev in model_router.chat_stream("tool_use", messages, tools=_fc_tools()):
                if ev["type"] == "fc_tool_calls":
                    calls = ev["calls"][:_MAX_CALLS]
                elif ev["type"] == "meta":
                    provider = ev["provider"]
                elif ev["type"] == "content":
                    answer += ev["delta"]
                    yield ev
                else:
                    yield ev   # reasoning / error 等原样透传
        except Exception as e:
            log.warning("fc stream round %s failed: %s", _round, e)
            break
        if answer.strip() or not calls:
            break   # 模型直接作答，或 FC 不可用（无内容也无调用）→ 跳出
        executed = [_exec(c, utterance, user_id, refs) for c in calls]
        tool_calls.extend(executed)
        yield {"type": "tools", "tool_calls": executed}
        messages.append({"role": "assistant", "content": "", "tool_calls": [
            {"id": c["id"], "type": "function",
             "function": {"name": c["name"], "arguments": c.get("arguments") or "{}"}}
            for c in calls]})
        messages.extend({"role": "tool", "tool_call_id": c["id"],
                         "content": json.dumps(e["result"], ensure_ascii=False)}
                        for c, e in zip(calls, executed))

    # 无回答，或 FC 只口头承诺没执行（关键词命中时）→ 走兜底补工具结果
    if not answer.strip() or (not tool_calls and _is_promise(answer) and _match(utterance)):
        if tool_calls:
            # FC 已执行过工具但轮数用尽：让模型基于工具结果做最终总结（防止模仿出 <tool_call> 文本）
            messages.append({"role": "user",
                             "content": "请根据以上工具执行结果，用中文自然语言回答用户的问题；不要再调用工具。"})
        else:   # FC 没执行过工具时才走关键词兜底（防重复写库）
            kw_calls = []
            for name in _match(utterance)[:_MAX_CALLS]:
                entry = _exec({"name": name, "arguments": "{}"}, utterance, user_id, refs)
                kw_calls.append(entry)
                tool_calls.append(entry)
            if kw_calls:
                yield {"type": "tools", "tool_calls": kw_calls}
                block = "\n".join(f"[{t['tool_name']}] {t['result']}" for t in kw_calls)
                messages.append({"role": "user",
                                 "content": f"工具执行结果：\n{block}\n\n用户问题：{utterance}"})
        for ev in model_router.chat_stream("general", messages):
            if ev["type"] == "meta":
                provider = ev["provider"]
            elif ev["type"] == "content":
                answer += ev["delta"]
                yield ev
            elif ev["type"] == "reasoning":
                yield ev

    if not answer.strip():   # 全部在线模型挂了：最后试本地离线模型（mimo9b，断网/断API也能答）
        try:
            for ev in model_router.chat_stream("offline", messages):
                if ev["type"] == "meta":
                    provider = ev["provider"]
                elif ev["type"] == "content":
                    answer += ev["delta"]
                    yield ev
                elif ev["type"] == "reasoning":
                    yield ev
        except Exception as e:
            log.warning("offline stream failed: %s", e)

    if not answer.strip():
        answer, provider = _DEMO, "demo"
        yield {"type": "content", "delta": answer}
    yield {"type": "done", "answer": answer, "provider": provider,
           "actions_taken": [t["tool_name"] for t in tool_calls if t["status"] == "ok"],
           "needs_confirm": False, "action_id": secrets.token_hex(4)}
