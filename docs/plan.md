# 安答（Anda）：校园 AI Agent 助手 · 项目规划与实现现状

> **文档性质变更（2026-11-01）**：本文原为纯规划文档，现已更新为"规划 vs 实现现状"对照版——
> 规划中已落地的标注 ✅，偏离规划实现的标注 ⚠️，未实现的标注 ⬜。
> 项目全景总览见 [PROJECT\_SUMMARY.md](PROJECT_SUMMARY.md)，接口契约见 [contract.md](contract.md)。

***

## 一、项目定位

**痛点**：现有校园 AI（安工小智）仅支持单轮检索式应答，回答局限于制度条文，无法结合个人课表与作息，只能被动等待提问。

**方案**：将 Agent 架构引入校园场景。学生通过网页以一句自然语言完成课表导入、提醒设置、办事查询、文档解析、代码生成等任务，系统自动完成意图识别 → 任务拆解 → 工具调用 → 结果汇总。

**创新点**：

1. **场景创新**：从"被动问答"到"主动服务"——依据课表在每节课前结合场景主动提醒（⬜ 定时推送闭环未完成，见 §六）；
2. **技术创新**：从"单轮检索"到"Agent 编排"——依托校园知识库将办事查询从"条文级"细化到"动作级"（✅ knowledge 工具 + 向量检索已落地）。

**技术特色** ✅：云端模型（智谱 GLM / SiliconFlow 星辰）+ 本地 Ollama 混合部署，按"能力权重"自动路由与降级——断网/断 API 也能回答（三层兜底链）。

***

## 二、目录结构：规划 vs 实际

### 规划的目录结构（原版）

```
Anda/
├── Frontend/          前端：静态页面 + 少量 JS
├── Backend/           后端：FastAPI 应用主体
│   ├── app.py         应用入口
│   ├── config.py      配置加载
│   ├── models/        数据库模型：用户/课表/提醒/备忘/任务/对话
│   ├── routes/        接口层
│   ├── service/       业务逻辑
│   ├── security/      认证与安全（规划独立模块）
│   ├── email/         邮件通知
│   └── task/          定时任务调度（课前提醒推送）
├── AI/                AI 端：意图识别 + 工具编排 + 模型调度（重写后：能力权重路由）
├── MCP/               Model Context Protocol 服务端
├── skill/             技能注册与管理系统
├── scripts/           运维脚本
├── test/              测试
└── OCR/               OCR 服务
```

### 实际目录结构（现状）

```
Anda/
├── Frontend/          ✅ 纯静态 HTML/JS + Vite 开发服务器（生产形态待定）
├── Backend/           ✅ FastAPI 应用主体
│   ├── app.py         ✅ 入口 + lifespan（init_db + health.start）
│   ├── config.py      ✅ .env 加载与常量
│   ├── database.py    ✅ SQLAlchemy 引擎与 Session（规划中无此文件）
│   ├── models/        ✅ user / schedule / reminder / memo / chat（任务并入备忘）
│   ├── routes/        ✅ auth / agent / schedule / reminder / memo / upload / nav / asr
│   ├── service/       ✅ auth / agent / schedule / reminder / memo / nav / chat_history
│   │                     / upload / email / ics
│   └── （security/、email/、task/ 未按规划拆分——安全并入 service/auth_service，
│        邮件并入 service/email.py，定时调度 未实现）
├── AI/                ✅ models.json + model_router + orchestrator + prompts + health
├── tool/              ✅ 8 个工具模块（见 模块四）
├── Data/              ✅ app.db / Knowledge.db / uploads/{user_id}/
├── docs/              ✅ 本目录
└── ⚠️ MCP/、skill/、scripts/、test/、OCR/ 均未创建（暂不实现）
```

> **偏离说明（为什么这样做）**：MCP 与独立 skill 系统被统一网关（models.json 能力权重路由）+ 扁平 tool 目录
> 取代——单机项目引入 MCP 进程间通信只增加复杂度；OCR 不单独起服务，以"ocr 能力槽位"并入模型路由与工具。

***

## 三、技术选型（✅ 全部落地）

| 项    | 规划                 | 实际                                                               |
| ---- | ------------------ | ---------------------------------------------------------------- |
| 框架   | FastAPI            | ✅ FastAPI（同步栈 + 流式 SSE）                                          |
| 前端   | HTML/JS 静态页 + Vite | ✅ 一致                                                             |
| 数据库  | MySQL  （SQLite）    | ⚠️ 目前使用SQLite                                                    |
| ORM  | SQLAlchemy         | ✅ SQLAlchemy                                                     |
| 认证   | JWT（无状态）           | ⚠️ 改为服务端 Bearer token（存 user.session\_token，24h）——单机场景更简单，撤销即时生效 |
| 密码   | bcrypt             | ⚠️ 改为 PBKDF2-HMAC-SHA256（120k 迭代 + 盐），标准库实现零依赖                   |
| 邮件   | SMTP               | ✅ QQ 邮箱 SMTP                                                     |
| 模型接入 | 多厂商 SDK            | ✅ 统一 OpenAI 兼容协议（云端 + Ollama 本地共用一个 client）                      |
| 意图识别 | 规划为独立路由层           | ⚠️ 由模型 Function Calling 主导 + 关键词匹配兜底（实测结论：规则路由覆盖面追不上自然语言）        |

***

## 四、功能模块实现状态

| 模块         | 规划接口                                                           | 状态                                                                       |
| ---------- | -------------------------------------------------------------- | ------------------------------------------------------------------------ |
| 认证         | register/verify/login/logout/me/update + forgot/reset password | ✅ 全部实现（邮件激活/重置，SMTP 未配置时降级开发模式链接）                                        |
| 智能体        | chat（规划无流式）                                                    | ✅ 超出规划：chat / **chat/stream(SSE)** / history / history/{chat\_id}，14 个工具 |
| 课表         | courses CRUD + today                                           | ✅ 节次制 weekday(1-7)+slot(1-12)，AI 抽取 + 防幻觉校验（错误码 12-17/28/29）             |
| 提醒         | reminder CRUD                                                  | ✅ set/get/{id}/done/undo                                                 |
| 备忘         | memo CRUD                                                      | ✅                                                                        |
| 任务         | task CRUD（独立模块）                                                | ⚠️ 未独立实现，并入备忘（memo）                                                      |
| 上传         | upload/list/download/delete                                    | ✅ 10MB 上限 + 后缀白名单 + 按用户隔离                                                |
| 导航         | nav                                                            | ✅ 高德 geocode/poi/route（amap\_mcp 直连非 MCP）                                |
| 语音         | 规划未提                                                           | ✅ 超出规划：/asr（SiliconFlow ASR 链）                                           |
| OCR        | 独立 OCR/ 服务                                                     | ⚠️ 并入模型路由 ocr 槽位 + MinerU 文档解析（doc\_parse 工具）                            |
| 知识库        | 办事指南"动作级"问答                                                    | ✅ knowledge 工具：Knowledge.db + bge-m3 向量检索 + 摘要改写                         |
| 日历导出       | 规划未提                                                           | ✅ 超出规划：ics\_service 导出 .ics 订阅文件                                         |
| 翻译/生图/代码生成 | 规划未细化                                                          | ✅ translation / image\_gen（Kolors+CogView 自管链）/ code\_gen 工具             |

### 统一响应与错误码 

- service 返回 `{ok, data}`，routes 包裹为 `{code, message, data}`（code=0 成功）；
- 错误码分段：1x 抽取链路 / 2x 提醒课程 CRUD / 4x 上传，详见 [Error\_code\_documentation.md](../Error_code_documentation.md)。

***

## 五、核心机制（已落地，详见 contract.md）

1. **能力权重路由**：models.json 登记模型×能力×权重，请求按权重降序逐个调用，第一个成功即返回；权重编码 fallback 顺序（数据来源：真实调用实测，星辰首块 1.9s 优于 glm-4.7-flash 免费额度 429）。
2. **Agent 三层降级**：FC 主路径 → 关键词兜底（exclude 优先）→ 离线模型（Ollama mimo9b）→ demo 文案，接口永不抛异常。
3. **防幻觉闭环**：工具必返 `ok` 字段 → 编排器判定状态 → 模型只许基于真实结果宣称完成；`_is_promise()` 识别"口头承诺不执行"的 FC 抖动。
4. **对话记忆**：app.db/chat\_message 单一真相源，跨设备同步，流式 finally 保证断连落库。

