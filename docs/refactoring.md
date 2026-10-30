# AI 端重构 · 接口契约文档

> 目标：删除 `AI/` 与 `tool/` 全部旧代码后重写。
> 本文档列出**必须保持兼容的对外契约**（Backend 保留不删，且它直接 import 了 AI 和 tool），
> 以及**新架构建议的内部接口设计**（参考：多模型统一网关 + 模型注册表 + 路由规则）。
>
> ⚠️ 核心原则：Backend 不动的前提下，下文第二、三章的函数签名与数据结构**一个都不能变**，
> 否则 `Backend/app.py`、`agent_service.py`、`schedule_service.py`、`reminder_service.py`、`nav_service.py` 会直接 ImportError。
>
> 📌 **函数级调用契约的最终权威版本见 `contract.md`**（含实测行号、认知修正与待核对项）；
> 本文聚焦架构与配置规范，两者有出入时以 contract.md 为准。

---

## 一、当前依赖关系总览（删库前必看）

| Backend 调用方 | 依赖的 AI/tool 接口 |
|---|---|
| `Backend/app.py` | `AI.health.start()`（lifespan 启动）、`AI.model_router.status()`、`tool.web_search.status()`（/health 接口） |
| `Backend/service/agent_service.py` | `AI.memory.recall/remember`、`AI.orchestrator.TOOLS`（注册 9 个工具）、`AI.orchestrator.run(...)` |
| `Backend/service/schedule_service.py` | `AI.model_router.chat(messages)` → `(text, provider)` |
| `Backend/service/reminder_service.py` | `AI.model_router.chat(messages)` → `(text, provider)` |
| `Backend/service/nav_service.py` | `tool.amap_mcp.geocode / search_poi / route` |
| `Frontend/pages/agent_ai.html` | 工具名 `web_search` 等用于展示（名字须保留） |

---

## 二、AI 包对外契约（重写后必须实现）

### 2.1 `AI.health`

```python
def start() -> None
```
- 在 FastAPI lifespan 中调用，负责启动后台健康检查线程（非阻塞）。
- 新架构中可在此同时实现 `model.json / routes.json` 的**配置热加载监听**。

### 2.2 `AI.model_router`

```python
def chat(messages: List[dict]) -> Tuple[Optional[str], Optional[str]]
def status() -> dict
```
- `chat`：返回 `(回答文本, "provider:model_id" 标识)`；全部模型失败返回 `(None, None)`。
  - 调用方：schedule_service.py:128、reminder_service.py:151，拿到 `text` 后直接做 JSON 解析（课程/提醒提取）。
  - **新架构建议**：扩展可选参数 `capability: str = ""`、`model_id: str = ""`，默认行为与旧版一致（默认路由）。
- `status`：返回 `{model_id: {"ok": bool, "checked_at": "HH:MM:SS"}}`，被 `/health` 接口原样返回给前端。

### 2.3 `AI.orchestrator`

```python
TOOLS: dict   # 工具注册表，agent_service 启动时会往里塞 9 个工具

def run(user_id: int, utterance: str, context=None, ref_block: str = "", refs=None) -> dict
```

**`TOOLS` 注册表结构**（agent_service.py:12-97 写入，orchestrator 只读）：

```python
orchestrator.TOOLS["工具名"] = {
    "desc": str,              # 工具描述（喂给 function calling 的 description）
    "keywords": tuple[str],   # 离线兜底意图匹配关键词
    "exclude": tuple[str],    # 排除词
    "fn": Callable,           # 工具函数，签名见第三章
}
```

现有 9 个工具名（**名字不能改**，前端展示 + 离线路由都依赖）：
`schedule_query`、`schedule_add`、`memo_list`、`reminder_set`、`reminder_query`、`doc_parse`、`image_understand`、`web_search`、`code_gen`

**`run()` 返回结构**（agent_service 直接透传给 `/agent/chat` 接口 → 前端渲染）：

```python
{
    "answer": str,                  # 最终回答文本（模型不可用时给演示文案，不能返回 None）
    "tool_calls": [ {"tool_name": str, "status": "success"|"failed", "result": dict} ],
    "actions_taken": [str],         # 人类可读的动作描述
    "needs_confirm": bool,          # 目前恒为 False，保留字段
    "action_id": str,               # 本次执行唯一 ID（旧版用 secrets.token_hex(4)）
    "provider": str,                # "provider:model_id"，用于前端显示本次由谁作答
    # 新架构建议追加：{"degraded": bool}  是否走了 fallback 降级
}
```

**`run()` 内部语义要求**：
1. 主路径：function calling（模型带工具表调用，多轮，单轮最多 4 次工具调用，最多 2 轮）；
2. FC 不可用时**离线兜底**：用 `TOOLS[name]["keywords"]/["exclude"]` 对 utterance 做关键词匹配选工具 → 直接执行 → 把工具结果拼进 prompt 再要一次普通回答；
3. 全挂时返回演示文案，**绝不抛异常**（这是 agent 接口可用性的底线）。

### 2.4 `AI.memory`

```python
def recall(user_id: int) -> List[dict]        # → [{"role": "user"|"ai", "content": str}]
def remember(user_id: int, utterance: str, answer: str) -> None
```
- 内存版对话历史，每用户保留 12 条（6 轮）。
- agent_service.chat() 里 `memory.recall(user.id)` 的结果会作为 `context` 传入 `orchestrator.run`，
  最终由 prompt.build_messages 转 role：`"ai" → "assistant"`。

### 2.5 `AI.prompt`（内部模块，但建议保留同等职责）

```python
MODEL_PROMPT: str          # 系统提示词（安答人设 + 工具使用原则 + 防幻觉约束）
def build_messages(utterance: str, context: Optional[List[dict]] = None) -> List[dict]
# → [{"role":"system",...}, {"role":"assistant",...}×N, {"role":"user",...}]，上下文窗口 6 条
```

---

## 三、tool 包对外契约（重写后必须实现）

### 3.1 工具函数统一签名（被 orchestrator.TOOLS 注册）

```python
def xxx_tool(utterance: str, user_id: int, refs=None) -> dict
```
- `utterance`：FC 模式下是模型生成的 task 描述；离线兜底模式下是用户原话。
- `refs`：本次对话引用的文件名列表。
- 返回 dict：成功 `{"ok": True, ...结果}`；失败 `{"ok": False, "error": str, "hint": str}`。
- ⚠️ 提示词里明确要求：写库类工具必须返回 `ok:true/false`，模型据此决定是否声称"已完成"，
  所以**返回结构里的 ok 字段是防幻觉机制的一部分，不能省**。

### 3.2 各工具职责与 AI 侧需求

| 工具 | 函数 | 依赖的 AI 能力 |
|---|---|---|
| `web_search` | `web_search.search_tool` + 模块级 `search(query, max_results)`、`probe_down()`、`status()`（/health 用） | 无（纯 HTTP 聚合：qianfan→anysearch→bing→ddg，带冷却降级） |
| `doc_parse` | `doc_parse.doc_parse_tool` | 调用 MinerU API（MINERU_API_KEY），可能需要普通 chat 做总结 |
| `image_understand` | `image_understand.image_understand_tool` | **vision 能力**：`model_router.chat(messages, capability="vision")`，messages 里含 base64 图片 |
| `code_gen` | `code_gen.code_gen_tool` | **代码生成**：`model_router.chat(messages, capability="code")` |

### 3.3 `tool.amap_mcp`（nav_service 直接调用，非 orchestrator 工具）

```python
def geocode(address: str, city: str = None) -> dict | None
def search_poi(keyword: str, city: str = None) -> dict | None
def route(origin: str, dest: str, mode: str) -> dict        # mode: walk/bus/drive/riding
```
- 依赖 `.env` 的 `AMAP_MAPS_API_KEY`。
- nav_service 的容错逻辑会处理 None，返回 None 表示"未获取到"。

---

## 四、新架构内部接口设计（文章方案的落地）

### 4.1 `AI/model.json` —— 模型注册表（已创建）

字段约定（以现有文件为准，把 `ability` 定为标准字段名）：

```json
{
    "model_id":    "工作台内部唯一标识",
    "provider":    "ollama | zhipu | siliconflow | deepseek | dashscope",
    "endpoint":    "OpenAI 兼容基础地址（不带 /chat/completions）",
    "api_key_env": "环境变量名（密钥永不入配置文件），本地模型留空",
    "model_name":  "传给供应商的真实模型名",
    "timeout":     "秒",
    "ability":     {"能力名": 权重1-10, "...": "..."},
    "default":     "true 为无能力匹配时的最终兜底"
}
```

> **能力级权重**（已替代旧的全局 weight 字段）：
> `ability` 是 `{能力名: 权重}` 映射，只登记该模型真正具备的能力；
> 请求某能力时，所有具备该能力的模型按**权重从高到低依次调用**，第一个成功即返回——
> 权重本身编码了 fallback 顺序，无需手写 fallback 链。
> 能力清单与各模型权重见 `AI/模型列表.md`。

> 注意：Ollama 的 `http://localhost:11434/v1` 是 OpenAI 兼容端点，统一客户端可直接覆盖，
> **不再需要单独的 ollama.py**（非流式 `/v1/chat/completions` 与 GLM/DeepSeek/SiliconFlow 完全同构）。

### 4.2 路由决策（能力权重驱动，routes.json 变为可选）

调用链直接由 `model.json` 的能力权重推导，**不再需要手写 routes.json**：

```
1. 显式指定：请求带 model_id → 直接路由该模型，不做匹配
2. 能力匹配：请求带 capability（如 "tool_use" / "vision" / "code"）
   → 收集 ability 中含该能力的模型 → 按该能力权重降序排列 → 依次调用，第一个成功即返回
   → 同权重时按注册顺序
3. 默认路由：无 capability 或无能力命中 → default 标记的模型；
   失败后按 "chat" 能力权重降序继续尝试
```

- 全部失败返回 `(None, None)`，响应中带 `degraded: true` 标记走了降级路径。
- `routes.json` 仅在需要**特例覆盖**时才创建（如"某类请求强制只走某模型"），默认不存在。
- 离线场景：本地模型登记 `"offline": 10`，云模型全挂时由离线路由选中。

### 4.3 建议的新文件结构

```
AI/
├── __init__.py
├── model.json          # 模型注册表（已创建）
├── routes.json         # 路由规则（可选，能力权重方案下默认不需要）
├── registry.py         # 加载/热重载 model.json + routes.json
├── provider.py         # 统一 OpenAI 兼容客户端（chat / chat_with_tools，一个文件覆盖所有云厂商+Ollama）
├── router.py           # 路由决策 + fallback 链 + 健康冷却表（对应旧 model_router）
├── orchestrator.py     # FC 管线 + 离线关键词兜底（对外契约同 2.3）
├── memory.py           # 对话历史（契约同 2.4）
├── prompt/
│   └── prompt.py       # 系统提示词（契约同 2.5）
└── health.py           # 健康巡检线程 + 配置热加载（契约同 2.1）
```

### 4.4 统一 provider 客户端核心签名

```python
def chat(messages: List[dict], entry: dict, temperature: float = 0.7) -> Optional[str]
def chat_with_tools(messages: List[dict], tools: List[dict], entry: dict) -> Optional[dict]
# entry 即 model.json 里的一条注册表记录；密钥从 os.environ[entry["api_key_env"]] 取
# URL 拼接：f"{entry['endpoint'].rstrip('/')}/chat/completions"
# 返回 None 表示该模型本次不可用（交由 router 走 fallback）
```

---

## 五、`.env` 依赖清单（config.py 已读取，重写时按需取用）

| 变量 | 用途 |
|---|---|
| `GLM_API_KEY` / `GLM_URL` / `GLM_MODEL` 等 | 智谱 OpenAI 兼容端点 |
| `SILICONFLOW_API_KEY` | SiliconFlow（OpenAI 兼容，可代理 DeepSeek/Qwen 等） |
| `OLLAMA_URL` | 本地模型 |
| `QIANFAN_AI_SEARCH_KEY` / `ANY_SEARCH_KEY` | 搜索源 |
| `MINERU_API_KEY` / `MINERU_MODEL` | 文档解析 |
| `AMAP_MAPS_API_KEY` | 高德 MCP |

> 新架构建议：模型列表全部移入 model.json 后，config.py 只需保留 `api_key_env` 指向的变量名存在即可。

---

## 六、重构验收清单

- [ ] `python -c "from AI import health, model_router, orchestrator, memory"` 无 ImportError
- [ ] `from tool import web_search, doc_parse, image_understand, code_gen, amap_mcp` 无 ImportError
- [ ] 启动 Backend 后 `GET /health` 返回 models + search 状态
- [ ] `/agent/chat` 闲聊可答（走 default 路由）
- [ ] 断掉主模型后回答正常且 `provider` 显示 fallback 模型
- [ ] "提醒我明天8点开会" 离线兜底路径能触发 `reminder_set` 工具
- [ ] 返回体包含 answer / tool_calls / actions_taken / action_id / provider 全字段
