register.html / forgot-password.html -> vite proxy -> 8000 -> app.py -> auth.py
  -> auth_service.py -> email_service.py -> QQ邮箱SMTP        
reset-password.html -> vite proxy -> 8000 -> app.py -> auth.py -> auth_service.py
  -> user.py -> database.py -> app.db <-| 返回

index.html -> vite proxy -> 8000 -> app.py -> auth.py -> auth_service.py
  -> user.py -> database.py -> app.db <-| 返回（session_token 存前端 localStorage）

agent_ai.html --POST /agent/chat--> vite proxy -> 8000 -> app.py
  -> auth.py -> auth_service.py<-| 401
  -> agent.py -> agent_service.py
        |-> upload_service.py
        |-> memory.recall()
        v
     orchestrator.py
        |-> prompt.py（build_messages  messages）
        |-> model_router.py-> glm.py / ollama.py
        v                                             
     response <-| 返回 -> agent_service.py -> memory.remember() -> 前端

agent_ai.html --POST/GET/DELETE /upload...--> vite proxy -> 8000 -> app.py
  -> auth.py -> upload.py -> upload_service.py -> Data/uploads/{user_id}/ <-| 返回

app.py lifespan -> health.py 每60秒 model_router.probe_down()

config.py config/database/glm/ollama/model_router... import
app.py GET /health -> model_router.status()
