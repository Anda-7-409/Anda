# 错误代码文档

> 本文档由全项目检索生成（2026-10-30），错误码已去重，与代码一一对应。
> 分段规则：**1x** = AI 抽取链路，**2x** = 提醒/课程增删改查，**4x** = 文件上传；`0` 成功，`1` 路由层通用失败。

## 错误代码列表

| 段 | 错误码 | 含义 | 触发位置 |
|---|---|---|---|
| - | 0 | 成功 | 各 routes |
| - | 1 | 通用失败 | 各 routes 的 `err()` |
| 1x | 11 | 无可用模型，已切换演示模式 | `AI/model_router.py` |
| 1x | 12 | 抽取模型暂不可用 | schedule / reminder 的抽取工具 |
| 1x | 13 | 没有成功识别用户意图 | schedule / reminder 的抽取工具 |
| 1x | 14 | 抽取信息不全 | schedule / reminder 的抽取工具 |
| 1x | 15 | 抽取结果字段异常 | `schedule_service.add_tool` |
| 1x | 16 | 缺少课程名称 | `schedule_service.add_tool` |
| 1x | 17 | 星期几超出范围 | `schedule_service.add_tool` |
| 1x | 18 | 提醒时间格式无法识别 | `reminder_service.set_tool` |
| 1x | 19 | 提醒创建失败 | `reminder_service.set_tool` |
| 1x | 28 | 节次需在 1-12 之间 | `schedule_service.add_tool` |
| 1x | 29 | 结束节次不能早于开始节次 | `schedule_service.add_tool` |
| 2x | 20 | 提醒内容不能为空（新建） | `reminder_service` |
| 2x | 21 | 时间格式不对（新建） | `reminder_service` |
| 2x | 22 | 提醒不存在或不属于你 | `reminder_service` |
| 2x | 23 | 提醒内容不能为空（更新） | `reminder_service` |
| 2x | 24 | 时间格式不对（更新） | `reminder_service` |
| 2x | 25 | 提醒不存在或不属于你（更新/删除） | `reminder_service` |
| 2x | 26 | 结束节次不能早于开始节次（CRUD 层） | `schedule_service.add_course` |
| 2x | 27 | 课程不存在或不属于你 | `schedule_service` |
| 4x | 40 | 文件名不能为空 | `upload_service` |
| 4x | 41 | 暂不支持该文件格式 | `upload_service` |
| 4x | 42 | 文件是空的 | `upload_service` |
| 4x | 43 | 文件超过 10MB 上限 | `upload_service` |
| 4x | 44 | 删除文件失败 | `upload_service` |
| 4x | 45 | 文件不存在或已被删除 | `upload_service` |

## 错误代码详细信息与解决方法

### 1x — AI 抽取链路

#### code 11 : 无可用模型，已切换演示模式

- **HTTP 状态码**：477（自定义），响应带 `"demo": true`
- **触发位置**：[AI/model_router.py](AI/model_router.py) `/ai/chat`；`NoModelError` 由路由层转出
- **可能的问题**：
  1. 环境变量未配置：`GLM_API_KEY` / `SILICONFLOW_API_KEY` 缺失，云端模型被过滤
  2. 本地 Ollama 未启动（`http://localhost:11434` 不通）
  3. 所有模型超时 / 401 Key 无效 / 429 限流 / 5xx
  4. 请求体缺少 `messages` 字段
  5. `ability` 拼写错误，无模型拥有该能力权重
- **解决方法**：
  1. 检查环境变量（PowerShell：`echo $env:GLM_API_KEY`）
  2. 确认 Ollama 运行中：`curl http://localhost:11434/api/tags`
  3. 访问 `GET /health` 查看各模型状态
  4. 核对 `AI/models.json` 的 `ability_weights`

#### code 12 / 13 / 14 : 抽取链路通用错误（schedule 与 reminder 共用）

schedule `add_tool`（[schedule_service.py:132](Backend/service/schedule_service.py#L132) 起）与 reminder `set_tool`（[reminder_service.py:157](Backend/service/reminder_service.py#L157) 起）共用同一组语义：

| 码 | 含义 | 原因 | 解决方法 |
|---|---|---|---|
| 12 | 抽取模型暂不可用 | 同 code 11（Key 缺失 / Ollama 未启动 / 网络超时） | 同 code 11；或走手动接口：`POST /schedule/courses`、`POST /reminder/set` |
| 13 | 没有成功识别用户意图 | 话术模糊 / 模型输出非 JSON | 按 `hint` 追问后重试；频繁出现时调 `models.json` 的 `reasoning` 权重 |
| 14 | 抽取信息不全 | 模型返回 `{"error": ...}`，缺必填字段 | 按 `hint` 追问缺失字段；`error` 内含模型给出的具体原因 |

#### code 15 ~ 17 / 28 / 29 : 课程抽取校验错误（schedule 专属）

- 15 抽取结果字段异常（[schedule_service.py:148](Backend/service/schedule_service.py#L148)）：模型 JSON 缺字段或类型不对，响应带 `raw` 原文，建议重新组织话术
- 16 缺少课程名称：追问课程名
- 17 星期几超出范围：weekday 必须在 1-7
- 28 节次需在 1-12 之间：`start_slot` / `end_slot` 越界
- 29 结束节次不能早于开始节次：调整节次顺序

#### code 18 / 19 : 提醒抽取错误（reminder 专属）

- 18 时间格式无法识别（[reminder_service.py:165](Backend/service/reminder_service.py#L165)）：要求 `HH:MM` 或 `YYYY-MM-DD HH:MM`
- 19 提醒创建失败：CRUD 层 `set_reminder` 失败，`error` 内含原因

### 2x — 提醒 / 课程增删改查

- 20/23（新建/更新时提醒内容为空）、21/24（时间格式不对）、22/25（提醒不存在或不属于你）：参数校验与归属校验错误，按 `message` 提示用户修正即可。新建与更新路径使用不同码以便前端区分场景。
- 26 结束节次不能早于开始节次（[schedule_service.py:41](Backend/service/schedule_service.py#L41)）：与 29 同语义，26 在 CRUD 层、29 在抽取层，按调用入口区分。
- 27 课程不存在或不属于你：检查课程 ID 与登录用户。

### 4x — 文件上传

- 40 文件名不能为空、41 格式不支持（服务端白名单）、42 文件为空、43 超过 10MB：上传前先做前端校验可避免。
- 44 删除失败：查看 `message` 中的异常信息，多为磁盘权限问题。
- 45 文件不存在或已被删除：确认文件名（含扩展名）正确、未被删除。

## 备注

- **同码多处属正常复用**（语义完全相同）：40（上传/删除两路径）、20/23、21/24（新建/更新两路径）、25（更新/删除两路径）、12/13/14（schedule/reminder 两工具）。
- 新增错误码请按分段规则取号（1x/2x/4x 顺延），并在本文档登记。
- 若 reminder 抽取工具将来合并入 schedule 的通用抽取层，12/13/14 无需变动。
