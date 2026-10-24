### 项目计划

```
思路：针对安工小智仅支持单轮检索式应答，且回答局限于制度条文，无法结合个人课表与作息相结合，只能被动等待提问——本项目开发“安答：校园AI Agent助手”，将Agent架构引入校园场景。学生通过网页以自然语言导入课表、设置提醒、发起咨询，系统自动完成意图识别、任务拆解与工具链调用；服务端采用云端 GLM API 与本地 Ollama 模型混合部署——通用咨询问答经本地模型处理，而课表、作业、考试、复习计划等复杂任务则通过云端调用以保证准确度。在每节课前进行主动提醒，实现从“被动问答”到“主动服务”的升级。
创新点：
1. 场景创新——从“被动问答”到“主动服务”：系统根据课表，在每节课前自动根据场景提醒，提高用户效率
2. 技术创新——从“单轮检索”到“Agent编排”：以“意图识别 → 任务拆解 → 工具调用 → 结果汇总”的Agent流水线替代单轮检索式问答，一句自然语言即可驱动课表解析、日程写入、提醒设置、复习计划生成等多个工具协同完成；依托知识库，将办事查询从“条文级”细化到“动作级”（去哪办、带什么、先办什么），并支持办事材料的格式本地转换。
作品概要：
1. 项目介绍：一款面向校园时间管理与办事场景的网页端AI Agent。学生以一句自然语言即可完成课表导入、作业与考试提醒设置、复习计划生成及办事流程“动作级”查询；系统采用知识库与“分级混合”的双模型部署，。Agent在本地记忆用户通勤节奏，每节课前自动推荐最晚出发时间，实现从“被动问答”到“主动服务”的升级
```

<br />

### 项目结构：

-Data-  //数据库与用户信息存放地点 改用 单一 SQLite + 多表 或 PostgreSQL ，避免多`.db` 文件管理连接池、事务一致性麻烦；`upload/` 目录需做权限隔离、文件类型校验、病毒扫描
        app.db (统一数据库（多表）) //用于存储所有用户数据，包括用户偏好设置，用户课表，用户提醒设置，用户复习计划，用户咨询记录等
        knowledge.db (知识库) //用于存储系统知识库，包括制度条文、办事流程等
        -upload-  //用户上传文件存放地点
                {user_id}/{file_name}  //用户提问AI上传的文件，包括文件路径、文件名、文件类型等
        
-Backend-  //后端模块
        app.py (主程序) //用于初始化数据库连接、处理用户请求、调用其他模块等  # FastAPI/Flask 工厂
        config.py (配置文件) //用于配置数据库连接、模型路径、知识库路径等全局参数
        database.py (数据库连接) //用于初始化数据库连接、创建数据库表等操作

        -models- (ORM 模型) //用于定义数据库表结构，仅用于课表
                __init__.py (模型初始化) //用于初始化模型模块，包括数据库连接、模型加载等操作
                schedule.py (用户课表模型) //用于定义用户课表结构，包括用户ID、课程名称、教师、时间、地点等字段
                user.py (用户模型) //用于定义用户信息结构，包括用户名、密码、邮箱等字段

        -routes- (用户模块) //用于处理用户相关操作，包括登录注册、课表管理、提醒设置、复习计划、咨询记录、任务记录等
            auth.py (用户认证) //用于用户登录注册、验证用户身份等操作
            schedule.py (用户课表管理) //用于管理用户课表，包括导入、查询、修改等操作
            reminder.py (用户提醒设置) //用于管理用户提醒设置，包括作业、考试、复习等
            review.py (用户复习计划) //用于管理用户复习计划，包括复习时间、复习内容等
            consult.py (用户咨询记录) //用于管理用户咨询记录，包括咨询内容、咨询时间、咨询状态等
            task.py (用户任务记录) //用于管理用户任务记录，包括任务类型、任务内容、任务状态等

        -service- (业务逻辑层) //用于处理用户请求，包括登录注册、课表管理、提醒设置、复习计划、咨询记录、任务记录等
                __init__.py (业务逻辑初始化) //用于初始化业务逻辑模块，包括数据库连接、模型加载等操作
                base.py (基础业务逻辑) //用于处理基础业务逻辑，包括用户认证、课表管理、提醒设置、复习计划、咨询记录、任务记录等
                auth_service.py (用户认证业务逻辑) //用于处理用户认证相关业务逻辑，包括登录、注册、验证用户身份等操作
                schedule_service.py (用户课表业务逻辑) //用于处理用户课表相关业务逻辑，包括导入、查询、修改等操作
                reminder_service.py (用户提醒业务逻辑) //用于处理用户提醒相关业务逻辑，包括设置、查询、修改等操作
                review_service.py (用户复习计划业务逻辑) //用于处理用户复习计划相关业务逻辑，包括设置、查询、修改、删除等操作
                consult_service.py (用户咨询记录业务逻辑) //用于处理用户咨询记录相关业务逻辑，包括咨询、查询、修改、删除等操作
                task_service.py (用户任务记录业务逻辑) //用于处理用户任务记录相关业务逻辑，包括设置、查询、修改、删除等操作
                OCR_service.py (用户 OCR 业务逻辑) //用于处理用户 OCR 任务相关业务逻辑，包括任务类型、任务内容、任务状态等操作
                agent_service.py (用户智能体业务逻辑) //用于处理用户智能体相关业务逻辑，包括智能体管理、智能体任务等操作
                email_service.py (邮件发送业务逻辑) //用于通过QQ邮箱SMTP（smtp.qq.com:465 SSL）发送注册激活链接与密码重置链接，发件账号与授权码从 .env 读取
                
-Frontend-  //前端模块
        index.html (前端网页) //用于显示项目介绍、登录注册入口等   @
        package.json (前端依赖管理) //用于管理前端依赖，包括框架、库等插件   
        <!-- npm install (安装前端依赖) //用于安装前端依赖，包括框架、库等插件
        npm run dev (启动前端开发环境) //用于启动前端开发环境，包括热更新、错误提示等功能 -->
        vite.config.js (Vite 配置文件) //用于配置 Vite 环境，包括插件、路径别名等
        <!-- npm run build (构建前端代码) //用于构建前端代码，包括压缩、合并等操作 -->
        <!-- npm run preview (预览前端代码) //用于预览前端代码，包括热更新、错误提示等功能 -->

            -assets- (静态资源模块) //用于存放前端静态资源，如图片、字体、图标等 @

            -pages- (页面模块) //用于处理用户操作，包括登录注册、课表管理、提醒设置、复习计划、咨询记录、任务记录等（登录功能已并入 index.html：JS fetch 调用 /auth/login，token 存 localStorage，后续请求带 Authorization 头）@
                register.html (注册页面) //用于用户注册，包括用户名、密码、邮箱等信息（注册成功后提示查收激活邮件，需点击邮件链接激活后才能登录） @
                forgot-password.html (忘记密码页面) //用于输入注册邮箱并请求发送密码重置链接（调用 POST /auth/forgot-password） @
                reset-password.html (重置密码页面) //从邮件重置链接打开（?token=xxx），输入新密码完成重置（调用 POST /auth/reset-password）@
                agent_ai.html (用户课表页面) //通过三栏布局用户上传的文件关于对话历史、日程提醒、AI对话、工具调用等集成到一个页面 @
                task_detail.html (用户任务详情页面) //用于显示用户任务的详细信息，如任务类型、任务内容、任务状态等

-skill-  //技能模块
        __init__.py (初始化数据库,统一调用连接) //用于初始化技能模块，确保所有技能相关操作在统一的连接下进行
        base.py (基础技能) //用于处理基础任务，如登录注册、课表管理、提醒设置、复习计划、咨询记录、任务记录等
        search.py (用户查询任务调用) //用于处理用户查询任务，如查询课表、查询提醒等
        system.py (系统任务调用) //用于处理系统任务，如日程写入、提醒设置等任务
        gpa.py (用户GPA计算) //用于计算用户GPA，根据用户成绩与课程学分计算
        review.py (用户复习计划生成) //用于生成用户复习计划，包括复习时间、复习内容等
-MCP-  //MCP模块
        __init__.py (初始化数据库,统一调用连接) //用于初始化MCP连接，确保所有MCP相关操作在统一的连接下进行
        base.py (基础MCP) //用于处理基础任务，如登录注册、课表管理、提醒设置、复习计划、咨询记录、任务记录等
        mcp_map.py (调用高德地图的mcp接口) //用于调用高德地图的mcp接口，获取用户位置信息、查询地图、导航路径等
        mcp_weather.py (调用天气mcp接口) //用于调用天气mcp接口，获取用户天气信息
-AI-  //AI模块
        __init__.py (初始化数据库,统一调用连接) //用于初始化AI连接，确保所有AI相关操作在统一的连接下进行
        model_router.py (模型路由) //用于路由用户任务到不同的模型，如glm模型、ollama模型等  如果电脑上没有 ollama或调用失败，则自动使用 glm模型 @
        glm.py (调用glm模型) //用于调用glm模型，处理用户任务，如查询课表、查询提醒等任务 @
        ollama.py (调用ollama模型) //用于调用ollama模型，处理用户任务，如查询课表、查询提醒等任务 @
        memory.py (上下文记忆) //用于存储用户上下文信息，如用户课表、用户提醒设置、用户复习计划等 
        orchestrator.py (任务协调器) //用于协调用户任务，如查询课表、查询提醒等任务，调用glm模型或ollama模型处理,能够让AI使用Agent 

        -OCR- (OCR模块) //用于识别用户上传的课表图片，提取课程信息、时间、地点等
            ocr.py (OCR识别) //用于调用OCR模型，识别用户上传的课表图片，提取课程信息、时间、地点等

        -prompt- (提示词模块) //用于生成AI模型的提示词，包括用户输入、系统知识库等信息 @
            prompt.py (提示词生成) //用于根据用户输入、系统知识库等信息生成AI模型的提示词，确保模型能够正确理解用户需求 @
        
-cloudflared_tunnel  //Cloudflare Tunnel模块
        start.bat (启动Cloudflare Tunnel) //用于启动Cloudflare Tunnel

-scripts-  //脚本模块
        migrate.py (数据库迁移脚本) //用于迁移数据库，确保数据库表结构与项目需求一致
        seed.py (数据库种子脚本) //用于初始化数据库，填充初始数据，确保用户能够正常使用项目
        schedule.py (任务调度脚本) //用于调度用户任务，如查询课表、查询提醒等任务，确保用户能够及时获取信息

-test-  //测试模块
        test.py (测试脚本) //用于测试项目功能，确保项目在不同环境下正常运行

-docs-  //文档模块
        README.md (项目说明文档) //用于介绍项目功能、使用方法、配置信息等
        API.md (API文档) //用于介绍项目提供的API接口，包括请求参数、响应格式、错误码等
        DATABASE.md (数据库文档) //用于介绍项目数据库表结构，包括字段、索引、约束等
        plan.md (项目计划文档) //用于介绍项目的开发计划、包括功能模块、技术栈、时间表等
        reminder.txt (用户提醒文档) //用于保存开发过程中所遇到的问题、解决方法等，方便后续开发

requirements.txt  //项目依赖模块 用于指定项目依赖的Python库，确保项目在不同环境下正常运行
.env.example  //环境变量配置示例（含 QQ_EMAIL_USER / QQ_EMAIL_AUTH_CODE 邮箱SMTP配置、GLM API Key、数据库连接等）
.env (环境变量配置) //用于配置环境变量，如API密钥、数据库连接信息、QQ邮箱SMTP发件账号与授权码等，确保项目在不同环境下正常运行

### 接口信息
        -auth (认证模块)   --Post,Post,Get,Post,Get,Put,Post,Post   ## 1. 认证模块 /auth（对应 routes/auth.py）
            /login (登录接口) # 请求体 {username, password}  --返回{code,message,data:{token,expires_in}}  //用于用户登录，返回token和过期时间（未激活账号拒绝登录并提示查收激活邮件）
            /register (注册接口) # 请求体 {username, password, email}  --返回{code,message}  //用于用户注册：创建未激活账号，并通过QQ邮箱SMTP发送激活链接（/auth/verify?token=xxx），用户点击邮件链接完成激活
            /verify (邮箱激活接口) --Get # 邮件激活链接打开 ?token=xxx  --校验通过后激活账号，302跳转到 /index.html  //注册激活链接落地接口
            /logout (退出登录接口) # 请求体 None  --返回{code,message}  //用于用户退出登录，返回成功信息
            /me (获取用户信息接口) # 请求体 None  --返回{code,message,data:{user_id,username,email}}  //用于获取用户信息，返回用户ID、用户名、邮箱
            /update (更新用户信息接口) # 请求体 {username?,email?,password?}  --返回{code,message}  //登录后修改个人信息（字段均可选）
            /forgot-password (忘记密码接口) # 请求体 {email}  --返回{code,message}  //通过QQ邮箱SMTP发送密码重置链接（链接指向 /pages/reset-password.html?token=xxx）
            /reset-password (重置密码接口) # 请求体 {token, new_password}  --返回{code,message}  //凭邮件链接中的一次性token重置密码
<!-- 邮箱流程说明：① 注册/重置均通过QQ邮箱SMTP发送链接（smtp.qq.com:465 SSL，发件账号+授权码从 .env 读取，授权码≠QQ登录密码）② 激活与重置 token 存于 user 表（verify_token/reset_token/token_expires），15分钟有效、一次性使用 -->
<!-- 认证方式：除`/auth/*` 外，所有接口要求 Header`Authorization: Bearer <token>`；2026-10-22 与实现对齐：请求体/路径不再传 token_id -->
        -schedule (课表模块)   --Post Get DELETE   ## 2. 课表模块`/schedule` （对应`routes/schedule.py` @ 已实现；身份走 Authorization 头；字段采节次制 weekday(1-7)+start_slot/end_slot(1-12) ）
            /courses (手动添加课程接口) --Post # 请求体 {name, teacher, classroom, weekday, start_slot, end_slot}  --返回{code,message,data:{course}}  //手动添加课程 @已实现
            -import (导入课表接口) --Post Post 
                /image (导入课表图片接口) # 请求体 {multipart/form-data:file}  --返回{code,message,data:{courses}}  //导入课表图片并解析课程信息；TODO 待OCR接入（视觉模型槽 GLM_MODEL_PICTURE_UNDERSTAND）
                /confirm (确认导入课表接口) # 请求体 {courses:[{name, teacher, classroom, weekday, start_slot, end_slot}]}  --返回{code,message}  //预览+确认两步走，改完再入库；TODO 随OCR一并实现
            /courses (查询课表接口) --Get # 请求体 None  --返回{code,message,data:{courses}}  //全周课表，按星期+节次排序 @已实现
            -courses (课程管理接口) --PUT DELETE
                /{course_id} (修改课程接口) # 请求体 {name?, teacher?, classroom?, weekday?, start_slot?, end_slot?}  --返回{code,message}  //按 course_id 修改；TODO
                /{course_id} (删除课程接口) --Delete # 请求体 None  --返回{code,message}  //按 course_id 删除自己的课程 @已实现
            /today (查询今日课表接口) --Get # 请求体 None  --返回{code,message,data:{courses}}  //右栏“今日日程”数据源 @已实现
        
 <!-- 图片导入拆成「预览 + 确认」两步，让用户改完再入库，确保用户课表信息与数据库保持一致 -->

        -reminder (提醒模块)   --Post Get PUT DELETE PUT ## 3. 提醒模块`/reminder` （对应`routes/reminder.py` ）
            /set (设置提醒接口) # 请求体 {reminder_type, reminder_time}  --返回{code,message}  //用于用户设置提醒，返回成功信息
            /get (获取提醒接口) # 请求体 None  --返回{code,message,data:{reminders}}  //返回当前用户全部提醒
            /{reminder_id} (修改提醒接口) # 请求体 {reminder_type?, reminder_time?}  --返回{code,message}  //按 reminder_id 修改
            /{reminder_id} (删除提醒接口) # 请求体 None  --返回{code,message}  //按 reminder_id 删除
            /{reminder_id}/done (确认提醒接口) # 请求体 None  --返回{code,message}  //用于用户确认提醒
            /{reminder_id}/undo (取消提醒接口) # 请求体 None  --返回{code,message}  //用于用户取消提醒
        
        -review (复习模块)   --Post Get PUT DELETE ## 4. 复习模块`/review` （对应`routes/review.py` ）
            /generate (生成复习表接口) # 请求体 None（初版基于课表自动生成，具体入参实现时定）  --返回{code,message}  //用于用户生成复习表
            /get (获取复习表接口) # 请求体 None  --返回{code,message,data:{reminders}}  //返回当前用户的复习表
            /{review_id} (修改复习表接口) # 请求体 {reminders:[{reminder_type, reminder_time}]}  --返回{code,message}  //按 review_id 修改
            /{review_id} (删除复习表接口) # 请求体 None  --返回{code,message}  //按 review_id 删除

        -consult (咨询模块)   -- Get Get DELETE ## 5. 咨询模块`/consult` （对应`routes/consult.py` ）
            /consult (咨询接口) # 请求体 {question}  --返回{code,message,data:{answer}}  //用于用户咨询，返回咨询答案
            /list (查询咨询接口) # 请求体 None  --返回{code,message,data:{consults}}  //返回当前用户的咨询历史
            /{consult_id} (删除咨询接口) # 请求体 None  --返回{code,message}  //按 consult_id 删除

        -task (任务模块)   -- Get Get DELETE ## 6. 任务模块`/task` （对应`routes/task.py` ）
            /task (查询任务接口) # 请求体 None  --返回{code,message,data:{tasks}}  //Agent 执行过的任务列表（`?type=&status=` 过滤）
            /{task_id} (任务详情接口) # 请求体 None  --返回{code,message,data:{task}}  //任务详情（含工具调用链）
        
        -agent (智能体模块)   -- Post Post Get ## 7. 智能体模块`/agent` （对应`routes/agent.py` ）
            /chat (智能体接口)  # 请求体 {utterance, context?}  --返回{answer, tool_calls:[{tool_name, status, result}], actions_taken, needs_confirm, confirm_payload}
            /confirm (确认智能体危险操作接口)  # 请求体 {confirm_token}  --返回{answer, tool_calls:[{tool_name, status, result}], actions_taken, needs_confirm, confirm_payload}  //用于用户确认智能体危险操作，返回成功信息       
            /stream (智能体流式接口)  # 请求体 {utterance, context?}  --返回{answer, tool_calls:[{tool_name, status, result}], actions_taken, needs_confirm, confirm_payload}  //用于用户智能体流式输出，返回智能体流式输出

        -upload (上传模块)   -- Post ## 8. 上传模块`/upload` （对应`Data/upload/{user_id}`返回 file_id））

        -frontend (前端模块)   -- Get Get  
            /     # index.html 
            /pages/{name}  //静态页面路由（FastAPI`StaticFiles` 挂载即可， 不用手写 ）

        -APScheduler (定时触发模块)  
<!-- 定时触发`scripts/scheduler.py` 每分钟扫描：① 课前提醒（查课表+天气+通勤→推送）② 到点提醒（查 reminder 表） -->
## 提醒
    1.前端样式文件到最后修改添加，在目前只需实现功能即可