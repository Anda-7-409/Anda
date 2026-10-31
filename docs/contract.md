# 安答跨模块函数级契约清单（现状版 · 2026-11-01 校订）

> 本文档曾是 AI 端重写前的"宪法"（重写期间任何函数签名改动必须先改本文再动代码）。
> **重写已完成（commit 0c132ca）**，本文已按当前代码全面校订，作为现存权威契约维护。
> 演进记录见 [refactoring.md](refactoring.md)，全景见 [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md)。

---

## A. 存活的外部契约（Backend ↔ AI ↔ tool 实际调用）

| 调用方 | 被调 | 契约（签名 → 返回） |
|---|---|---|
| Backend/app.py lifespan | `AI.health.start()` | 启动健康巡检守护线程 |
| Backend/app.py `/health` | `AI.model_router.status()` | `→ {"ok": bool}`（仅 API key 配置检查） |
| Backend/app.py `/health` | `tool.web_search.status()` | `→ {"qianfan": bool, "anysearch": bool}` |
| Backend/routes/asr.py | `AI.model_router.transcribe(path)` | 音频文件路径 → 转写文本 |
| Backend/service/agent_service.py | `AI.orchestrator.run(utterance, user_id, context)` | `→ {"answer", "tool_calls", "actions_taken", "needs_confirm", "action_id", "provider"}` |
| Backend/service/agent_service.py | `AI.orchestrator.run_stream(utterance, user_id, context)` | 事件流：`tool_start / tools / content / reasoning / done` |
| Backend/service/agent_service.py | `AI.prompts` / `Backend/service/chat_history_service` | 提示词插值 / 记忆窗口 `recall_window(db, user_id)` 与落库 |
| Backend/service/agent_service.py | `tool.amap_mcp.geocode(addr, city) / search_poi(q, city) / route(origin, dest, mode, city)` | `→ dict`（经 nav_service 包装为 nav 工具） |
| Backend/service/schedule_service.py | `AI.model_router.chat("reasoning", messages)` | `→ (msg_dict, provider)`，取 `msg.get("content")` 解析 JSON |
| Backend/service/reminder_service.py | `AI.model_router.chat("reasoning", messages)` | 同上 |
| tool/* | `AI.model_router.chat("code"\|"vision"\|"general"\|"translation", messages)` | 同上，失败抛 `NoModelError`（工具自行捕获转 `ok: False`） |
| tool/knowledge.py | `AI.model_router.embed(texts)` | `→ list[vector]`（bge-m3） |
| tool/image_gen.py | 自管 HTTP 链（Kolors → CogView） | 非 chat 端点，不走能力路由 |

**变更点（相对重写前）**：`chat(messages)` → `chat(ability, messages, tools)`；返回由 `(text, provider)` 改为 `(msg_dict, provider)`；`AI.memory` 删除，记忆改由 chat_history_service + app.db/chat_message 承担。

---

## B. AI 内部契约（orchestrator ↔ model_router ↔ prompts）

- orchestrator 以 `model_router.chat("tool_use", messages, tools=fc_spec)` 发起 FC；`NoModelError` → 跳出主路径进兜底链；
- 兜底链顺序：**FC → 关键词匹配（exclude 优先）→ 离线模型（offline 权重）→ demo 文案**，任何一层失败不抛异常、静默降级；
- 流式 `run_stream` 事件命名固定：`tool_start`(names) → `tools`(tool_calls 结果) → `content`/`reasoning`(增量) → `done`(收尾)；`_exec` 保证工具异常转为 `{"ok": False, ...}`；
- 工具结果回填消息 `role:"tool"`，格式与 OpenAI 一致；
- prompts：`P(key, **kw)` 从 prompt.json 插值，缺 key 返回占位符不抛异常。

---

## C. 工具函数统一签名（14 个，两端同契约）

```python
def xxx_tool(utterance="", user_id=None, refs=None, **_) -> dict
```

- 入参：`utterance` 任务话术；`user_id` 用户主键；`refs` 引用文件名列表（≤5）；
- 出参：**必须含 `"ok": True/False`**——编排器据此判定工具状态，模型只许基于真实结果宣称完成（防幻觉闭环的基石）；
- 工具内部自行捕获一切异常 → `{"ok": False, "error": ...}`，绝不向编排器抛出。

| 工具名 | 所在文件 |
|---|---|
| schedule_query / schedule_add | Backend/service/schedule_service.py |
| reminder_set / reminder_query | Backend/service/reminder_service.py |
| memo_list | Backend/service/memo_service.py |
| calendar_export | Backend/service/ics_service.py |
| doc_parse | tool/doc_parse.py |
| image_understand | tool/image_understand.py |
| web_search | tool/web_search.py |
| code_gen | tool/code_gen.py |
| nav | Backend/service/nav_service.py（经 amap_mcp） |
| image_gen | tool/image_gen.py |
| knowledge | tool/knowledge.py |
| translation | tool/translation.py |

---

## D. tool/amap_mcp.py 内部契约

- `geocode(addr, city="") → {"location": "lng,lat"}`；
- `search_poi(q, city="") → {"name", "location", "address"}`（POI 名 → 坐标）；
- `route(origin, dest, mode="walk", city="") → {"mode", "distance", "duration", "steps"}`；
- 共性：`ok` 字段、失败 `error`、HTTP 层异常本地化（连接拒绝返回 `ok: False`）、超时 5s。

---

## E. 数据库与数据契约

- 用户数据隔离：所有业务表带 `user_id` 外键语义，路由层统一经 `get_current_user` 注入当前用户，查询必带 `user_id` 过滤（越权防线）；
- 对话记忆单一真相源：`app.db / chat_message` 表（chat_history_service 读写），含 reasoning 字段（重放思考面板）；
- 上传目录 `Data/uploads/{user_id}/`，引用经 `_build_ref_block` 注入对话上下文（≤5 个文件）。

---

## F. 统一响应契约

- service 层：`{"ok": bool, "data": ...}`；routes 层：`{"code": int, "message": str, "data": ...}`（code=0 成功）；
- 错误码分段见 [Error_code_documentation.md](../Error_code_documentation.md)（1x 抽取 / 2x CRUD / 4x 上传）。

---

## G. 重写期间的关键决策（已生效，留档）

1. ✅ 不用 MCP：单机项目，统一 OpenAI 协议网关替代进程间通信；
2. ✅ 不用厂商 SDK：云端 + 本地 Ollama 共用一个 httpx client；
3. ✅ 不做显式 fallback 链：能力权重编码调用顺序（models.json 数据驱动）；
4. ✅ 删除 AI/memory：记忆由 Backend chat_history_service 承担（持久化 + 跨设备）；
5. ✅ prompts 集中 prompt.json：改提示词不动代码；
6. ✅ 工具双端同契约：Backend service 工具与 tool/ 工具同表注册、同签名、同 ok 约定。
