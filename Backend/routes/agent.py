import json

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import agent_service, auth_service, chat_history_service

router = APIRouter()

class ChatRequest(BaseModel):
    utterance: str
    context: Optional[list] = None
    refs: Optional[list] = None
    chat_id: Optional[str] = None   # 前端对话 id：带上则服务端落库聊天记录

@router.post("/chat")
def chat(
    req: ChatRequest,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    result = agent_service.chat(db, user, req.utterance, req.context, req.refs, req.chat_id)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"code": 1, "message": result["message"], "data": None})
    return {"code": 0, "message": "ok", "data": result["data"]}

from fastapi.responses import StreamingResponse

@router.post("/chat/stream")
def chat_stream(req: ChatRequest,
                user: User = Depends(auth_service.get_current_user),
                db: Session = Depends(get_db)):
    if not req.utterance or not req.utterance.strip():
        return JSONResponse(status_code=400, content={"code": 1, "message": "内容不能为空哦 (。•́︿•̀。) 想聊点什么呀？", "data": None})
    def gen():
        for ev in agent_service.chat_stream(db, user, req.utterance, req.refs, req.chat_id):
            yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

# ===== 聊天记录：app.db/chat_message 单一真相源，跨设备同步 =====
@router.get("/history")
def get_history(user: User = Depends(auth_service.get_current_user),
                db: Session = Depends(get_db)):
    return {"code": 0, "message": "ok", "data": chat_history_service.build_history(db, user.id)}

@router.delete("/history/{chat_id}")
def delete_history(chat_id: str,
                   user: User = Depends(auth_service.get_current_user),
                   db: Session = Depends(get_db)):
    chat_history_service.delete_chat(db, user.id, chat_id)
    return {"code": 0, "message": "ok", "data": {"id": chat_id}}
