# AI 重构 · 函数级契约清单（重写宪法）

> 范围：方案一（去重 + 依赖单向化，目录结构不动）。
> 原则：**6 个存活文件的调用面 100% 兼容**，其余随重建发挥。
> 文档分工：架构与配置规范见 `refactoring.md`；**函数级契约以本文为准**。
> 行号依据：云端 e91e6ef 版本实测。

---

## A. 存活文件对 AI/ 的调用面（必须原样满足）

| 调用方 | 精确调用 | 契约要求 |
|---|---|---|
| `Backend/app.py:10-11` | `health.start()` | **幂等**（`_started` 防重入）；daemon 线程：启动即初测 + 每 **300s** 循环 `model_router.probe_down()` 与 `web_search.probe_down()`，各自 try/except 互不拖累 |
| `Backend/app.py:18-22` | `model_router.status()` / `web_search.status()` | `/health` 端点用，返回 **JSON 可序列化 dict**（内部形状重写时可自定） |
| `Backend/service/agent_service.py:128` | `memory.recall(user.id)` | → `List[{"role","content"}]`（返回副本，外部修改不影响内态） |
| `Backend/service/agent_service.py:130` | `memory.remember(user_id, utterance, answer)` | role 拼成 `"user"`/`"ai"`（**不是 assistant**）；容量上限见 G-2 |
| `Backend/service/agent_service.py:129` | `orchestrator.run(user_id, utterance, ctx, ref_block=..., refs=...)` | → dict，**6 个键不可少**：`answer` / `tool_calls[{tool_name,status,result}]` / `actions_taken` / `needs_confirm` / `action_id` / `provider`（`action_id = secrets.token_hex(4)`） |
| `Backend/service/agent_service.py:12-98` | `orchestrator.TOOLS["名"] = {desc, keywords, exclude, fn}` × **9** | 方案一将把 9 块声明搬走（见 F-1），但 `TOOLS` 容器名与 dict 结构**保持不变** |
| `Backend/service/reminder_service.py:151`、`schedule_service.py:128` | `text, provider = model_router.chat(messages)` | **二元组 `(str\|None, str)`**；调用方只用 `if not text` 判不可用 |
| `AI/health.py:14-29`（重写件） | `model_router.probe_down()` | 无参无返回值；启动与循环均调 |

## B. 被删文件夹内部的互约（AI/ 重写件之间）

```
orchestrator ──→ model_router.chat_with_tools(messages, schemas) → (msg|None, provider)
             ──→ model_router.chat(messages)                      → (text|None, provider)
             ──→ AI.prompt.prompt.build_messages(utterance, context) → List[{"role","content"}]
                   （ref_block 挂 messages[-1]；离线兜底路径对 ask 重新 build）
glm.py / ollama.py / model_router ──→ Backend.config（常量见各文件 import 行）
```

**认知修正 ①**：早期讨论提到的 `run()` 内 `refs` 未定义 NameError **已被上游修复**——现在 `run()` 签名含 `refs=None` 且一路透传到 `_exec_tool`。重建时这是**必须保留的正确行为**，不是要复刻的 bug。

## C. 工具函数签名契约（9 个工具统一）

```python
fn(utterance=task, user_id=user_id, refs=refs or []) -> dict   # orchestrator._exec_tool 全部 kwargs 调用
```

- **Backend 系 5 个**：`schedule_service.query_tool / add_tool`、`memo_service.list_tool`、`reminder_service.set_tool / query_tool`
- **tool 系 4 个**：`web_search.search_tool`（形参 `**_` 兼容）、`doc_parse.doc_parse_tool`、`image_understand.image_understand_tool`、`code_gen.code_gen_tool`
- 现行签名已统一为 `(utterance, user_id, refs=None)`；重写时保持 **kwargs 兼容**即可（`refs` 可选）

## D. tool/ 对外的其他契约（不经 TOOLS 直接被调）

| 模块 | 调用方 | 签名 |
|---|---|---|
| `amap_mcp` | `nav_service` | `geocode(addr, city=) → {ok, location, name\|error}`；`search_poi(q, city=) → {ok, pois:[{name,address,...}]\|error}`；`route(origin, dest, mode) → {ok, data\|error}` |
| `web_search` | `app.py` / `health.py` | `status() → dict`；`probe_down() → None` |

**认知修正 ②**：`TOOLS` 里**没有导航工具**——amap 只走 `routes/nav → nav_service` 直连。9 = 课表 2 + 提醒 2 + 备忘 1 + 文档 1 + 图片 1 + 搜索 1 + 代码 1。**重建时不要顺手新增工具**，新增即行为变更。

## E. 行为基线（重构验收对照，逐条测）

| # | 基线行为 | 出处 |
|---|---|---|
| 1 | `chat` 顺序 = 意图偏好（关键词命中→GLM 池优先）→ **冷却重排**（60s 失败冷却，可用者优先）。旧 `COMPLEX_KEYWORDS` 本身不重建，见 F-4 | model_router |
| 2 | FC 主路径**只走支持 tools 的池**；2 轮上限，第 3 次摘工具表收口 | orchestrator |
| 3 | `answer is None` → 关键词兜底（exclude 优先于 keywords 匹配）→ 仍 None → **演示文案兜底，绝不抛异常** | orchestrator |
| 4 | ref_block：主路径挂 `messages[-1]`、兜底路径拼进 ask；**永远不进历史轮** | orchestrator |
| 5 | 记忆：存取窗口数字见 G-2；role `user`/`ai` | memory + prompt |
| 6 | 空消息拦截在 service 层；service 返回 `{ok, data}`、routes 包 `{code, message, data}` | agent_service + routes |

## F. 方案一设计决策点（动工前定案）

1. **工具注册触发点**：9 块声明搬回各自实现模块（自注册，消灭 Backend→AI.orchestrator 的反向注入）。推荐：`tool/__init__.py` 聚合导入 5 个子模块；Backend service 靠既有 import 链触发。**硬要求：首个 `/agent/chat` 请求前 `TOOLS` 必须满员**（读取发生在请求时，import 顺序天然满足）。
2. **config 位置**：保留 `Backend/config.py`，记为**已知限制**（它是叶子模块，依赖语义实为"人人→配置"，病只在命名）。`AI.health → tool.web_search` 同理保留（探活是只读横切关注）。——这两条**文档化接受，不再列为待修**。
3. **Session 模式（修正）**：**不强行收敛**。请求作用域（routes→service）用 `get_db` 注入；工具函数运行在请求作用域之外，**自开 `SessionLocal`**。两种模式文档化并存；把 db 穿透 `run()` 签名属于契约破坏，禁止。
4. **关键词表（修正）**：旧 `model_router.COMPLEX_KEYWORDS` 的唯一职责是选模型，新架构由 `models.json` 的 `ability_weights` + `routes.json` 完全取代——**重建后自动消失**，不设替代品。
5. **统一工具签名**：C 表的 kwargs 形态是标准，重建及未来新增工具照抄。
6. **工具配置化（定案：不做）**：**不设 `tools.json`**。模型是纯配置实体，工具是代码实体（`fn` 无法进 JSON），配置化会让声明/实现分离换个文件类型复活（违反本文件 F-1）。如需可视化工具清单，加 `GET /agent/tools` 调试端点，从 `orchestrator.TOOLS` 动态生成——配置是输入，不是镜像。触发重新评估的条件：插件化需求 / 非程序员调关键词 / 工具数 30+。三者目前均不满足。

## G. 待核对项（开工对应 Step 时以云端原文为准）

1. **注册表文件名**：实际为 `AI/models.json`（非 model.json）。
2. **记忆窗口容量**：两处文档分别写"12 轮"与"12 条（6 轮）"——**Step 2（memory.py）开工时以云端 memory.py 原文实测为准**，本清单不预填数字。
