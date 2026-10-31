import json, secrets, logging, time
from AI import model_router, prompts
log = logging.getLogger("anda.orchestrator")
TOOLS = {}

_MAX_ROUNDS = 2   # function calling 最多轮数（契约 2.3：单轮≤4次工具调用，最多2轮——模型话痨也得给它立规矩）
_MAX_CALLS = 4

def _match(utterance: str):
    # 离线兜底：关键词匹配选工具（FC 不可用时才走这条老路，土是土了点但管用 (¬‿¬)）
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
    # 模型口头承诺要执行却没调工具（FC 抖动的经典表演）：有承诺词且没有给出任何真实链接/结果
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
    # 执行一次工具调用（FC 与关键词兜底共用）；模型提炼的 task 优先于用户原话，失败不抛出（ok 字段防幻觉——模型一上头就开始编，信不得）
    name = (call.get("name") or "").strip()
    t0 = time.monotonic()
    task_brief = (utterance or "").replace("\n", " ")[:40]
    log.info("工具调用开始 -> %s（user_id=%s，task=%s）(๑•̀ㅂ•́)و✧", name or "unknown", user_id, task_brief)
    try:
        args = json.loads(call.get("arguments") or "{}")
        if not isinstance(args, dict):
            args = {}
    except Exception:
        args = {}
    task = (args.get("task") or args.get("utterance") or "").strip() or utterance
    cfg = TOOLS.get(name)
    if not cfg:
        log.warning("工具调用失败 -> %s：未注册的工具 (＞﹏＜)", name or "unknown")
        return {"tool_name": name or "unknown", "status": "fail",
                "result": {"ok": False, "error": "未注册的工具"}}
    try:
        result = cfg["fn"](utterance=task, user_id=user_id, refs=list(refs or []))
    except Exception as e:
        log.warning("工具调用失败 -> %s：执行异常 %s（耗时 %.1fs）(╯°□°）╯︵ ┻━┻", name, e, time.monotonic() - t0)
        result = {"ok": False, "code": 51, "message": f"工具执行异常：{e}"}
    ok = bool(result.get("ok"))
    log.info("工具调用结束 -> %s：%s（耗时 %.1fs）", name,
             "成功" if ok else f"失败 ok={result.get('ok')} msg={str(result.get('message') or result.get('error') or '')[:80]}",
             time.monotonic() - t0)
    return {"tool_name": name, "status": "ok" if ok else "fail", "result": result}

def _normalize(ctx):
    # 记忆窗口里的 role 是 "user"/"ai"，OpenAI 兼容接口只认 assistant——不转的话接口直接闹脾气 (。•́︿•̀。)
    return [{"role": "assistant" if m.get("role") == "ai" else m.get("role", "user"),
             "content": m.get("content", "")} for m in (ctx or [])]

def run(user_id, utterance, ctx=None, ref_block="", refs=None):
    t0 = time.monotonic()
    log.info("Agent 开始 -> user_id=%s utterance=%s（refs=%d）(๑•̀ㅂ•́)و✧",
             user_id, (utterance or "").replace("\n", " ")[:40], len(refs or []))
    user_msg = f"{ref_block}\n\n{utterance}" if ref_block else utterance
    messages = [*_normalize(ctx), {"role": "user", "content": user_msg}]
    messages.insert(0, {"role": "system", "content": prompts.P("orchestrator.sys_fc")})
    tool_calls, answer, provider = [], "", ""

    # 主路径：function calling——模型自动识别要调的工具，结果回填后可继续调用（多轮）
    for _round in range(_MAX_ROUNDS):
        try:
            msg, provider = model_router.chat("tool_use", messages, tools=_fc_tools())
        except Exception as e:
            log.warning("FC 轮次 %s 调用失败 (＞﹏＜)：%s", _round, e)
            break
        tc_list = (msg.get("tool_calls") or [])[:_MAX_CALLS]
        if not tc_list:
            answer = (msg.get("content") or "").strip()
            log.info("FC 直答 -> 第 %d 轮模型未发起工具调用 (¬‿¬)", _round + 1)
            break
        calls = [{"id": tc.get("id", ""), "name": (tc.get("function") or {}).get("name", ""),
                  "arguments": (tc.get("function") or {}).get("arguments")} for tc in tc_list]
        log.info("FC 第 %d 轮 -> 发起 %d 个工具调用: %s (๑•̀ㅂ•́)و✧",
                 _round + 1, len(calls), [c["name"] for c in calls])
        executed = [_exec(c, utterance, user_id, refs) for c in calls]
        tool_calls.extend(executed)
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": tc_list})
        messages.extend({"role": "tool", "tool_call_id": c["id"],
                         "content": json.dumps(e["result"], ensure_ascii=False)}
                        for c, e in zip(calls, executed))

    # 无回答，或 FC 只口头承诺没执行（关键词命中时）→ 走兜底补工具结果（光说不练的家伙，兜底来治 (。•́︿•̀。)）
    if not tool_calls and answer and _is_promise(answer) and _match(utterance):
        log.info("承诺检测触发 -> 模型口头承诺未执行工具，走兜底 (´･ω･`)")
    if not answer or (not tool_calls and _is_promise(answer) and _match(utterance)):
        if tool_calls:
            # FC 已执行过工具但轮数用尽还没有回答：让模型基于工具结果做最终总结
            # （否则消息以 role:"tool" 结尾，无工具表的 general 调用会模仿出 <tool_call> 文本——被坑过才懂得设防）
            log.info("FC 总结 -> 工具已执行但无回答，让模型基于结果总结 (´･ω･`)")
            messages.append({"role": "user",
                             "content": prompts.P("orchestrator.fc_summary")})
        else:   # FC 不可用/未执行才走关键词兜底；已执行过工具就不重复执行（防重复写库，写重了数据就双倍快乐了）
            kw_names = _match(utterance)[:_MAX_CALLS]
            if kw_names:
                log.info("关键词兜底 -> 命中: %s (¬‿¬)", kw_names)
            for name in kw_names:
                tool_calls.append(_exec({"name": name, "arguments": "{}"}, utterance, user_id, refs))
            if tool_calls:
                block = "\n".join(f"[{t['tool_name']}] {t['result']}" for t in tool_calls)
                messages.append({"role": "user",
                                 "content": prompts.P("orchestrator.tool_result_block",
                                                      block=block, utterance=utterance)})
        try:
            msg, provider = model_router.chat("general", messages)
            answer = (msg or {}).get("content") or ""
        except Exception as e:
            log.warning("%s 模型调用失败 (＞﹏＜)：%s", provider, e)

    if not answer:   # 全部在线模型挂了：最后试本地离线模型（mimo9b，断网/断API也能答——压箱底的救命稻草 (´•̥ω•̥`)）
        log.info("离线降级 -> 在线链路无回答，尝试本地离线模型 (。•́︿•̀。)")
        try:
            msg, provider = model_router.chat("offline", messages)
            answer = (msg or {}).get("content") or ""
        except Exception as e:
            log.warning("%s 离线模型调用失败 (＞﹏＜)：%s", provider, e)

    if not answer:
        answer, provider = prompts.P("orchestrator.demo"), "demo"
        log.warning("演示兜底 -> 全部链路不可用，返回演示文案 (´•̥ω•̥`)")

    log.info("Agent 完成 -> provider=%s，工具 %d 次（成功 %d），answer %d 字，总耗时 %.1fs ヾ(≧▽≦*)o",
             provider, len(tool_calls),
             len([t for t in tool_calls if t["status"] == "ok"]), len(answer),
             time.monotonic() - t0)
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
    t0 = time.monotonic()
    log.info("Agent 开始（流式）-> user_id=%s utterance=%s（refs=%d）(๑•̀ㅂ•́)و✧",
             user_id, (utterance or "").replace("\n", " ")[:40], len(refs or []))
    user_msg = f"{ref_block}\n\n{utterance}" if ref_block else utterance
    messages = [*_normalize(ctx), {"role": "user", "content": user_msg}]
    messages.insert(0, {"role": "system", "content": prompts.P("orchestrator.sys_fc")})
    tool_calls, answer, provider = [], "", ""

    for _round in range(_MAX_ROUNDS):
        calls = []
        if _round == 1:   # 第 2 轮开考前递条子：结果已回填、直接作答（推理模型不再长考，肉眼可感的提速）
            messages.append({"role": "user", "content": prompts.P("orchestrator.fc_round2")})
        try:
            for ev in model_router.chat_stream("tool_use", messages, tools=_fc_tools()):
                if ev["type"] == "fc_tool_calls":
                    calls = ev["calls"][:_MAX_CALLS]
                    if calls:   # 模型已发起调用：先广播"正在调用工具"，执行完成再发 tools 结果
                        log.info("FC 第 %d 轮（流式）-> 发起 %d 个工具调用: %s (๑•̀ㅂ•́)و✧",
                                 _round + 1, len(calls), [c.get("name") for c in calls])
                        yield {"type": "tool_start",
                               "names": [c.get("name") or "unknown" for c in calls]}
                elif ev["type"] == "meta":
                    provider = ev["provider"]
                elif ev["type"] == "content":
                    answer += ev["delta"]
                    yield ev
                else:
                    yield ev   # reasoning / error 等原样透传
        except Exception as e:
            log.warning("FC 轮次 %s 调用失败 (＞﹏＜)：%s", _round, e)   
            break
        if not calls:
            if answer.strip():
                log.info("FC 直答（流式）-> 第 %d 轮模型未发起工具调用 (¬‿¬)", _round + 1)
            break   # 无调用：直接作答或 FC 不可用（无内容也无调用）→ 跳出走兜底
        # 注意：模型可能"引导文本 + 工具调用"同时输出（如先流式说"好的，帮你添加课表"
        # 再发起 image_understand）——此时 answer 非空但不能当直答跳出，工具必须执行；
        # 已流出的引导文本保留展示，第 2 轮的正式回答接在其后（被模型摆过一道换来的教训 (＞﹏＜)）
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

    # 无回答，或 FC 只口头承诺没执行（关键词命中时）→ 走兜底补工具结果（光说不练的家伙，兜底来治 (。•́︿•̀。)）
    if not tool_calls and answer.strip() and _is_promise(answer) and _match(utterance):
        log.info("承诺检测触发 -> 模型口头承诺未执行工具，走兜底 (´･ω･`)")
    if not answer.strip() or (not tool_calls and _is_promise(answer) and _match(utterance)):
        if tool_calls:
            # FC 已执行过工具但轮数用尽：让模型基于工具结果做最终总结（防止模仿出 <tool_call> 文本）
            log.info("FC 总结 -> 工具已执行但无回答，让模型基于结果总结 (´･ω･`)")
            messages.append({"role": "user",
                             "content": prompts.P("orchestrator.fc_summary")})
        else:   # FC 没执行过工具时才走关键词兜底（防重复写库，写重了数据就双倍快乐了）
            kw_calls = []
            kw_names = _match(utterance)[:_MAX_CALLS]
            if kw_names:
                log.info("关键词兜底 -> 命中: %s (¬‿¬)", kw_names)
                yield {"type": "tool_start", "names": kw_names}   # 与 FC 路径一致：执行前先广播"正在调用工具"
            for name in kw_names:
                entry = _exec({"name": name, "arguments": "{}"}, utterance, user_id, refs)
                kw_calls.append(entry)
                tool_calls.append(entry)
            if kw_calls:
                yield {"type": "tools", "tool_calls": kw_calls}
                block = "\n".join(f"[{t['tool_name']}] {t['result']}" for t in kw_calls)
                messages.append({"role": "user",
                                 "content": prompts.P("orchestrator.tool_result_block",
                                                      block=block, utterance=utterance)})
        for ev in model_router.chat_stream("general", messages):
            if ev["type"] == "meta":
                provider = ev["provider"]
            elif ev["type"] == "content":
                answer += ev["delta"]
                yield ev
            elif ev["type"] == "reasoning":
                yield ev

    if not answer.strip():   # 全部在线模型挂了：最后试本地离线模型（mimo9b，断网/断API也能答——压箱底的救命稻草 (´•̥ω•̥`)）
        log.info("离线降级 -> 在线链路无回答，尝试本地离线模型 (。•́︿•̀。)")
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
            log.warning("离线模型也挂了 (＞﹏＜)： %s", e)

    if not answer.strip():
        answer, provider = prompts.P("orchestrator.demo"), "demo"
        log.warning("演示兜底 -> 全部链路不可用，返回演示文案 (´•̥ω•̥`)")
        yield {"type": "content", "delta": answer}

    log.info("Agent 完成（流式）-> provider=%s，工具 %d 次（成功 %d），answer %d 字，总耗时 %.1fs ヾ(≧▽≦*)o",
             provider, len(tool_calls),
             len([t for t in tool_calls if t["status"] == "ok"]), len(answer),
             time.monotonic() - t0)
    yield {"type": "done", "answer": answer, "provider": provider,
           "actions_taken": [t["tool_name"] for t in tool_calls if t["status"] == "ok"],
           "needs_confirm": False, "action_id": secrets.token_hex(4)}
