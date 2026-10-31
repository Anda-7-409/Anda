# AI 端重构：现状与架构规范

> **文档性质变更（2026-11-01）**：重构已完成（commit `0c132ca` 删除旧 AI/tool 并重写）。
> 本文不再描述"重构计划"，而是描述**重构后的当前架构与契约**，与代码同步维护。
> 若本文与代码冲突，以代码为准并回改本文。函数级契约见 [contract.md](contract.md)。

---

## 一、架构现状

AI 端 = **统一 provider + 模型注册表 + 能力权重路由**：

- 所有 LLM（云端厂商 + 本地 Ollama）统一走 OpenAI 兼容协议 `/chat/completions`，共用一个 httpx client，无需任何厂商 SDK；
- 每个模型在 `AI/models.json` 登记：`model_id / provider / endpoint / api_key_env / model_name / timeout / ability_weights / default`；
- `ability_weights` 是 `能力名: 权重(1-10)` 映射——请求某能力时，具备该能力的模型**按权重降序依次调用，第一个成功即返回**，权重本身编码 fallback 顺序，不手写 fallback 链；
- 请求特征附在模型条目上（如 `stream_timeout`、`enable_thinking`），由网关透传；
- 无 API key 的模型自动跳过；本地 Ollama 登记 `offline: 10`，云全挂时兜底。

### 依赖总览（实际）

```
Backend/app.py        → AI.health.start()（lifespan 启动健康巡检线程）
Backend/app.py        → AI.model_router.status()、tool.web_search.status()（/health 端点）
Backend/routes/asr.py → AI.model_router.transcribe()（语音转写）
Backend/service/agent_service.py
                      → AI.orchestrator.run / run_stream（对话入口）
                      → AI.prompts（构建 system/工具结果模板）
                      → tool.amap_mcp（导航三接口直连，非工具注册）
                      → Backend/service/chat_history_service（对话记忆，单一真相源 app.db/chat_message）
Backend/service/schedule_service.py → AI.model_router.chat("reasoning", messages)（课表抽取）
Backend/service/reminder_service.py → AI.model_router.chat("reasoning", messages)（提醒抽取）
tool/*                → AI.model_router.chat("code"|"vision"|"general"|"translation") + embed()
tool/image_gen.py     → 自管源顺序（/images/generations 非 chat 端点，走不了能力链）
```

> ⚠️ 旧文档中的 `AI.memory` 已删除：记忆改由 Backend 的 chat_history_service + chat_message 表承担（跨设备同步）。
> ⚠️ `AI/routes.json` 为旧版按能力指定 target/fallback 的配置，**当前代码不加载它**（已被 ability_weights 取代），仅留档。

---

## 二、模块契约（当前实现）

### 2.1 AI/model_router.py

```python
chat(ability: str, messages: list, tools: list | None = None)
    → tuple[dict, str]        # (完整 message dict, provider 名)；全链失败抛 NoModelError
chat_stream(ability: str, messages: list, tools: list | None = None)
    → generator               # 依次 yield {"type":"meta",...}、{"type":"delta",...}、
                              #   {"type":"fc_tool_calls", "tool_calls":[...]}；
                              #   内部失败降级非流式 chat，再失败 yield 空（不抛）
status() → {"ok": bool}       # 仅检查 API key 环境变量是否配置（非真实探活）
transcribe(audio_path: str)   # ASR 链（星尘 ASR 系列，specialist 接口）
embed(texts: list) -> list    # bge-m3 嵌入（跳过非 embeddings 端点的模型）
NoModelError                  # 自定义异常：链上无可用模型
```

- 消息格式即 OpenAI 格式（role/content/tool_calls/tool_call_id/name）；
- 每次调用按 `ability_weights.get(ability, 0) > 0` 过滤模型并按权重排序，逐个尝试，异常/超时静默切下一个；
- `timeout` 与 `stream_timeout`（若有）分别控制普通与流式请求。

### 2.2 AI/orchestrator.py

```python
TOOLS: dict[str, dict]   # 工具注册表：{工具名: {"desc", "keywords", "exclude", "fn"}}

run(utterance: str, user_id: int, context: list | None = None) -> dict
    # 返回六键：answer / tool_calls / actions_taken / needs_confirm / action_id / provider
    # 流程：FC 主路径（chat("tool_use", tools=…)）→ 工具执行回填（≤2轮×4次）→
    #       关键词兜底（exclude 优先）→ 离线模型 → demo 文案；永不抛异常

run_stream(utterance, user_id, context) -> generator
    # 事件流：tool_start {"names"} / tools {"tool_calls"} / content / reasoning / done
    # 执行逻辑与 run() 对齐，语义相同
```

- FC 执行函数 `_exec(fn, task, user_id, refs)`：统一 `fn(utterance=task, user_id=..., refs=[...])` 调用；
- 工具未注册 / 参数解析失败 / 函数异常 → 返回 `{"ok": False, "status": "fail", "error": ...}`，不中断管线；
- `_is_promise()`：识别"模型口头承诺要执行但没调工具"的 FC 抖动（承诺词 + 无真实链接），触发兜底补执行。

### 2.3 AI/prompts.py + AI/prompt.json

```python
P(key, **kw) -> str   # 从 prompt.json 取提示词并插值；缺 key 返回占位符，不抛异常
```

现用 key：`orchestrator.sys_fc`（FC 系统提示词）、`fc_summary`、`fc_round2`、`tool_result_block`、`demo` 等。改提示词只动 prompt.json，不动代码。

### 2.4 AI/health.py

`start()` 启动守护线程周期巡检；异常模型应调 `model_router.probe_down(model_id)` 降权冷却。**当前 probe_down 为空实现、status 仅查配置——"健康检查形同配置检查"是已知遗留项**（见 PROJECT_SUMMARY.md §六）。

---

## 三、工具契约（tool/）

```python
def xxx_tool(utterance="", user_id=None, refs=None, **_) -> dict
    # 入参：utterance 任务话术；user_id 用户主键；refs 引用文件名列表（≤5）
    # 出参：必须含 "ok": True/False；失败附 "error"；前端/编排器依赖 ok 判定，禁止无 ok 返回
    # 工具内部自己捕获所有异常并转成 {"ok": False, "error": ...}，绝不向编排器抛异常
```

**当前注册的 14 个工具**（agent_service.py 注册进 TOOLS）：

| 工具名 | 实现 | 职责 |
|---|---|---|
| schedule_query / schedule_add | Backend/service/schedule_service.py | 课表查询 / AI 抽取添加（错误码 12-17/28/29） |
| reminder_set / reminder_query | Backend/service/reminder_service.py | 提醒设置（AI 抽取）/ 查询 |
| memo_list | Backend/service/memo_service.py | 备忘速查 |
| calendar_export | Backend/service/ics_service.py | 课表导出 .ics |
| doc_parse | tool/doc_parse.py | 文档抽取摘要（MinerU/本地解析 + LLM 摘要） |
| image_understand | tool/image_understand.py | 图片理解（vision 能力链） |
| web_search | tool/web_search.py | 联网搜索（千帆 AI 搜索 → AnySearch → DuckDuckGo 自管冷却链） |
| code_gen | tool/code_gen.py | 代码生成并存用户云盘 |
| nav | Backend/service/nav_service.py | 路线规划（amap_mcp 直连） |
| image_gen | tool/image_gen.py | 文生图（Kolors → CogView 自管链） |
| knowledge | tool/knowledge.py | 校园知识库问答（bge-m3 向量检索 + 摘要改写） |
| translation | tool/translation.py | 翻译（translation 能力链，Hunyuan-MT） |

> Backend 侧工具（schedule/reminder/memo/ics/nav）与 tool/ 侧工具契约完全一致，同表注册。

### tool/web_search.py 契约

```python
search(query, max_results=5) -> list   # 自管源链：qianfan → anysearch → ddg，失败源冷却跳过
probe_down(source) / status()          # 冷却标记 / 各源配置状态
```

---

## 四、环境变量（.env 实际所需）

```
QQ_EMAIL_ADDRESS / QQ_EMAIL_AUTH_CODE      # 注册激活、密码重置邮件（未配置则开发模式打印链接）
FRONTEND_BASE_URL                          # 激活/重置链接的站点根（默认 https://anda.dpdns.org）
GLM_API_KEY                                # 智谱 BigModel（models.json 多模型依赖）
SILICONFLOW_API_KEY                        # 硅基流动（默认主力 Xing4.0 依赖，务必配置）
MINERU_API_KEY                             # 文档解析（doc_parse 云端链）
AMAP_MAPS_API_KEY                          # 高德（导航 geocode/poi/route）
QIANFAN_AI_SEARCH_KEY / ANY_SEARCH_KEY     # 联网搜索两源（都有 DDG 兜底）
```

> Ollama 无需环境变量（endpoint 写在 models.json）。
> ⚠️ .env.example 需按上表补齐（已知遗留）。

---

## 五、待办（承接 PROJECT_SUMMARY.md §六）

- [ ] AI/routes.json 决定去留：已无代码引用，建议删除或文首标注"留档"；
- [ ] 实现 probe_down 真实探活（低频轻量调用）或如实标注 status 为"配置检查"；
- [ ] AI/ 补 `__init__.py`（tool/ 有，AI/ 靠命名空间包在跑，风格不一致）；
- [ ] model_router 内嵌独立 FastAPI `/ai/chat`（L95-122，从未挂载）建议删除；
- [ ] "调用时间权重"：按实测响应时间动态调整链序。
