# 安答（Anda）：校园 AI Agent 助手 · 项目总结

> 本文整合自 `docs/plan.md`（项目规划）、`docs/refactoring.md`（重构架构规范）、`docs/contract.md`（函数级契约）、
> `docs/remind.txt`（开发笔记/踩坑实测）、`docs/review.txt`（代码评审），并以 2026-11-01 全量代码检查结果为准校正。
> **定位：反映项目当前真实状态的唯一总览文档。** 规划与实现的差异均已标注。

***

## 一、项目定位与创新点

**痛点**：现有校园 AI（安工小智）仅支持单轮检索式应答，回答局限于制度条文，无法结合个人课表与作息，只能被动等待提问。

**方案**：将 Agent 架构引入校园场景。学生通过网页以一句自然语言完成课表导入、提醒设置、办事查询、文档解析、代码生成等任务，系统自动完成意图识别 → 任务拆解 → 工具调用 → 结果汇总。

**两大创新点**：

1. **场景创新——从"被动问答"到"主动服务"**：依据课表在每节课前结合场景主动提醒，提高用户效率；
2. **技术创新——从"单轮检索"到"Agent 编排"**：Agent 流水线替代单轮检索，依托校园知识库将办事查询从"条文级"细化到"动作级"（去哪办、带什么、先办什么）。

**技术特色**：云端模型（智谱 GLM / SiliconFlow 星辰）+ 本地 Ollama 混合部署，按"能力权重"自动路由与降级——断网/断 API 也能回答。

***

## 二、系统架构（现状实测）

```
┌─ Frontend ──────────── 纯静态 HTML/JS + Vite 开发服务器（5173，/auth /agent 等代理到 8000）
│    index.html（登录并入）· pages/agent_ai.html（三栏主页面：对话/日程/工具）
│    register / forgot_password / reset_password / task_detail
│
┌─ Backend (FastAPI, :8000) ────────────────────────────────────────
│    app.py（lifespan: init_db + health.start）· config.py（.env 加载）
│    database.py（SQLAlchemy + SQLite app.db）
│    routes/  auth · agent(含SSE流式) · schedule · reminder · memo · upload · nav · asr
│    service/ auth · agent(注册14个工具) · schedule · reminder · memo · nav
│              chat_history(对话记忆单一真相源) · upload · email · ics(日历导出)
│    models/  user · schedule · reminder · memo · chat
│
┌─ AI/ ─────────────────────────────────────────────────────────────
│    models.json（21个模型注册表：能力权重 ability_weights）
│    model_router.py（能力路由 + chat/chat_stream/embed/transcribe）
│    orchestrator.py（FC 编排 + 关键词兜底 + run/run_stream）
│    prompts.py + prompt.json（提示词集中管理）· health.py（健康巡检线程）
│
┌─ tool/ ───────────────────────────────────────────────────────────
│    web_search · doc_parse(MinerU) · image_understand · image_gen
│    code_gen · knowledge(校园知识库) · translation · amap_mcp(高德导航)
│
└─ Data/ ── app.db（统一业务库）· Knowledge.db · uploads/{user_id}/
```

### 一次对话的完整链路示例

```
用户输入 → Frontend (Bearer token + utterance/refs/chat_id)
        → POST /agent/chat/stream (SSE)
        → agent_service：构建 ref_block（引用文件内容）+ 从 chat_message 表取记忆窗口
        → orchestrator.run_stream：
            ① 主路径 FC：model_router.chat("tool_use") 按权重选模型，模型自主选工具
            ② 执行工具（tool/*.py 与 service/*_tool），结果以 role:"tool" 回填，可多轮（≤2轮×4次）
            ③ 兜底：FC 不可用 → 关键词匹配（exclude 优先）执行工具 → 拼结果再要一次回答
            ④ 再兜底：离线模型（Ollama mimo9b）→ 最后降级 demo 文案，绝不抛异常
        → 事件流式返回（tool_start/tools/content/reasoning/done），消息实时落库 app.db/chat_message
```

### 与早期契约文档的差异（重要）

contract.md/refactoring.md 写于重构前，部分契约已随实现演进，**以代码为准**：

| 契约文档说法                                           | 当前实现                                                                                  |
| ------------------------------------------------ | ------------------------------------------------------------------------------------- |
| `model_router.chat(messages) → (text, provider)` | `chat(ability, messages, tools) → (msg_dict, provider)`                               |
| TOOLS 共 9 个工具，无导航工具                              | **14 个工具**：课表2 + 提醒2 + 备忘1 + 日历导出1 + 文档1 + 图片理解1 + 生图1 + 搜索1 + 代码1 + 导航1 + 知识库1 + 翻译1 |
| `memory.recall/remember` 内存记忆                    | 改为 `chat_history_service`，app.db/chat\_message 表（跨设备同步）                               |
| status 返回 `{ok, checked_at}`                     | `status()` 返回最近一次低频探活结果 + `checked_at`（chat 模型每 5 分钟 1-token 探活，未探活能力为配置检查）           |
| 工具 status 值 `success/failed`                     | `ok/fail`（前端不依赖该字符串，无运行时影响）                                                           |
| health 线程调 `probe_down()` 做真实探活                  | 已实现：对已配密钥的 chat 模型发 1-token 探活请求，结果供 /health 展示（仅记录不熔断）                               |

***

## 三、核心机制设计

### 3.1 能力权重路由（受 OpenRouter 启发，自研）

- `models.json` 登记每个模型的 `ability_weights`（如 chat/tool\_use/reasoning/vision/code/asr/embedding/text\_to\_image）；
- 请求带能力名 → 收集具备该能力的模型 → **按权重降序依次调用，第一个成功即返回**——权重本身编码了 fallback 顺序；
- 无 API key 的模型自动跳过；本地 Ollama 登记 `"offline": 10`，云端全挂时兜底；
- 权重来自实测数据（remind.txt）：星辰 Xing4.0 首块 1.9s 且稳定，glm-4.7-flash 免费额度 429 频发且挂掉会阻塞链首 60-90s。

### 3.2 防幻觉闭环（本项目最核心的设计）

```
工具函数必须返回 {"ok": true/false, ...}
  → orchestrator 依 ok 判定工具 status
  → 模型只能基于真实工具结果宣称"已完成"，写库失败模型必须如实说失败
  → _is_promise() 额外识别"口头承诺要执行却没调工具"的 FC 抖动（承诺词+无真实链接），触发兜底补执行
```

### 3.3 认证与安全

- 密码：PBKDF2-HMAC-SHA256，12 万次迭代 + 每用户随机盐 + `compare_digest` 恒时比较；
- 会话：Bearer token 存 localStorage（`<img>` 标签带不上 Authorization 头，天然免疫经典 img-CSRF——review\.txt 结论），24h 有效，服务端查 `user.session_token` 校验；
- 注册激活/密码重置：QQ 邮箱 SMTP 发链接，token 15 分钟一次性；未激活账号可被同邮箱重新注册覆盖（自愈逻辑，解决"僵尸账号"问题）；
- 上传：路径净化（`Path.name`）+ 后缀白名单 + 10MB 上限 + 按 user\_id 目录隔离，无路径穿越；
- 数据隔离：所有业务接口统一走 `get_current_user` 依赖注入，按 user\_id 过滤。

### 3.4 请求/响应与错误码约定

- 统一包裹：service 层返回 `{ok, data}`，routes 层包成 `{code, message, data}`（code=0 成功）；
- 空消息拦截在 service 层；422 由 Pydantic 自动产出；
- 独立错误码分段：上传 40-45、课表抽取 12-17/28/29、模型不可用 11（详见 `Error_code_documentation.md`）。

***

## 四、功能模块与 API 一览（已实现）

| 模块  | 路由前缀        | 主要端点                                                                                         | 说明                                      |
| --- | ----------- | -------------------------------------------------------------------------------------------- | --------------------------------------- |
| 认证  | `/auth`     | register / verify(302激活) / login / logout / me / update / forgot\_password / reset\_password | 邮件激活+重置，未配置 SMTP 时降级为"开发模式链接"           |
| 智能体 | `/agent`    | chat / chat/stream(SSE) / history / history/{chat\_id}                                       | 14 个工具；流式含 reasoning 透传；历史跨设备同步         |
| 课表  | `/schedule` | courses(增/查/删) / today                                                                       | 节次制 weekday(1-7)+slot(1-12)，AI 抽取带防幻觉校验 |
| 提醒  | `/reminder` | set / get / {id}改删 / done / undo                                                             | <br />                                  |
| 备忘  | `/memo`     | 列表/增删改                                                                                       | <br />                                  |
| 上传  | `/upload`   | POST / GET列表 / download/{name} / DELETE                                                      | FileResponse attachment 下载              |
| 导航  | `/nav`      | 路线规划                                                                                         | 高德 geocode/poi/route                    |
| 语音  | `/asr`      | 音频转写                                                                                         | SiliconFlow ASR 链                       |
| 系统  | `/health`   | 模型+搜索状态                                                                                      | <br />                                  |

***

## 五、开发历程与关键决策（踩坑记录精选）

1. **AI 端整体重写**（0c132ca）：删除旧 AI/tool，改为"统一 provider + 能力权重路由 + 模型注册表"架构；Ollama 的 `/v1` 是 OpenAI 兼容端点，一个客户端覆盖所有云厂商+本地，不再需要单独的 ollama.py。
2. **注册僵尸账号自愈**：未激活账号占邮箱导致无法重注册 → 注册查重只拦已激活账号 + login 引导重发激活链接。遗留：换新邮箱+忘用户名时用户名被未激活记录永久锁死（见 §六）。
3. **关键词路由的局限**（实测案例）：上传图片的 ref\_block 占位文本拼进 utterance 后，"提醒"二字误触发 reminder\_set → 抽取失败 → 模型编造"仅支持文本文件"。结论：规则路由"零成本可控但覆盖面永远追不上自然语言"，规划中由 FC 主路径取代（已实现），关键词降级为兜底。
4. **模型权重调优**：glm-4.7-flash 加 `stream_timeout:15` + `thinking`，星辰加 `enable_thinking:true`，general 权重 10→5——依据实测 429 频发 vs 星辰 1.9s 首块。
5. **流式 reasoning 刷新后消失**：根因是存历史时丢了 reasoning → 前端 3 处修复（sendStream/send/appendMessage+selectChat），reasoning 随消息对象走存储链路，重放时重建折叠思考面板，向后兼容。
6. **DOM 调试教训**：不接进 DOM 树的节点更新一万次也不会渲染——"渲染问题先验证 DOM 挂接，再查网络"。
7. **生产部署形态**：开发期 Vite(5173)+FastAPI(8000) 双进程；生产可 `npm run build` 后由 FastAPI StaticFiles 单端口托管，Vite 退役（当前代码尚未挂载 StaticFiles，激活邮件链接依赖反向代理同源转发）。

***

## 六、已知问题与风险清单（2026-11-01 全量检查产出，按优先级）

### 高危（影响协作/可运行性）

| # | 问题                                                                                                                                             | 位置               | 修复方法                             |
| - | ---------------------------------------------------------------------------------------------------------------------------------------------- | ---------------- | -------------------------------- |
| 1 | 5 个核心文件未提交：AI/prompts.py、AI/prompt.json、Backend/routes/asr.py、Backend/service/ics\_service.py、tool/translation.py——已提交文件 import 它们，队友 clone 即崩 | git 工作区          | `git add` 这 5 个文件连同 17 个修改文件一起提交 |
| 2 | requirements.txt 缺 `python-dotenv`，新环境装完起不来                                                                                                    | requirements.txt | 补一行 `python-dotenv`              |

### 中危（功能/安全）

| # | 问题                                                                   | 位置                           | 修复方法                                                      |
| - | -------------------------------------------------------------------- | ---------------------------- | --------------------------------------------------------- |
| 3 | .env.example 过时：缺 SILICONFLOW\_API\_KEY（默认主力模型依赖）、MINERU/AMAP/搜索 key | .env.example                 | 按 refactoring.md §5 补齐变量名                                 |
| 4 | verify\_token 与 reset\_token 共用 `token_expires` 字段，重置密码会给旧激活链接"续命"   | auth\_service.py             | 拆分两个过期字段，或重置时清空 verify\_token                             |
| 5 | 登录/注册/忘记密码无速率限制；忘记密码暴露邮箱注册状态                                         | routes/auth.py               | IP+用户名计数限流；统一返回"若已注册将收到邮件"                                |
| 6 | 健康检查空转：probe\_down() 为 pass，status() 只查环境变量                          | health.py / model\_router.py | 实现轻量探活或如实标注"仅配置检查"                                        |
| 7 | SQLite 未开 WAL/busy\_timeout，流式落库+课表写入并发可能 database is locked         | database.py                  | connect\_args 加 timeout:30，启动执行 `PRAGMA journal_mode=WAL` |
| 8 | 遗留（remind.txt）：换邮箱+忘用户名 → 用户名被未激活记录永久锁死                              | register 逻辑                  | 注册时清理 token 超时的待激活账号                                      |

### 低危/规范

- model\_router.py 内嵌独立 FastAPI `/ai/chat`（L95-122）从未挂载，属死代码，建议删除；
- config.py 的 GLM\_*/OLLAMA\_* 常量重构后基本无人引用（配置已归 models.json），且与 app.py 的 load\_dotenv 重复加载 .env；
- refactoring.md/contract.md 契约描述与实现漂移（见 §二 差异表），建议同步或在文首加"以代码为准"声明；
- session/verify/reset token 明文入库（拖库即冒用）；update\_profile 把异常原文回传用户；logout 未校验 Bearer 前缀；多端登录互踢（单 session\_token 字段）；上传同名并发竞态；init\_db 冗余 import；AI/ 缺 `__init__.py`（靠命名空间包在跑）。

***

## 七、路线图（TODO）

- [x] 提交 5 个未跟踪文件 + 修复 requirements（立即）
- [x] 补齐 .env.example / 更新契约文档
- [ ] 接入课表图片导入：预览+确认两步走（视觉槽 GLM-4.6V-Flash / DeepSeek-OCR / PaddleOCR-VL 已在 models.json 就位）
- [ ] 课前主动提醒闭环：APScheduler 定时扫描（课表+天气+通勤→推送）——核心卖点"主动服务"尚缺定时触发器
- [ ] 路由增加"调用时间权重"（remind.txt TODO）：按实测响应时间动态调整链序
- [ ] 生产部署：StaticFiles 挂载 + 公网域名（anda.dpdns.org）+ cloudflared tunnel
- [ ] 评测数据化：20 张真实课表 + 20 条提醒指令实测抽取准确率，把"架构选型"变成答辩数据
- [ ] 测试体系：优先 orchestrator 意图识别 + 工具链编排的 mock 测试

***

## 八、快速上手

```bash
# 1. 环境（Python 3.11+）
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt   # 记得确认含 python-dotenv

# 2. 配置：复制 .env.example 为 .env，至少填 GLM_API_KEY 或 SILICONFLOW_API_KEY
#    （都不填也能跑：对话降级为演示模式）

# 3. 启动后端（项目根目录运行，模块方式启动）
.venv\Scripts\python -m Backend.app     # 127.0.0.1:8000，/health 查看模型状态

# 4. 启动前端（开发模式，另开终端）
cd Frontend && npm install && npm run dev   # 5173，已配置 /auth 等路径代理到 8000
```

> 生产模式：`npm run build` 后由 FastAPI StaticFiles 单端口托管（见 §五.7）。

***

*维护约定：本文为总览索引，细节仍以各专项文档 + 代码为准；架构变更时同步更新 §二 差异表与 §六 问题清单。*
