# agent.py (智能体模块) 对应 plan.md 第7节 /agent/chat；/confirm 与 /stream 待后续迭代
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import agent_service, auth_service

router = APIRouter()

class ChatRequest(BaseModel):
    utterance: str
    context: Optional[list] = None

@router.post("/chat")
def chat(
    req: ChatRequest,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    result = agent_service.chat(db, user, req.utterance, req.context)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"code": 1, "message": result["message"], "data": None})
    return {"code": 0, "message": "ok", "data": result["data"]}

# TODO /confirm：确认智能体危险操作（请求体 confirm_token）— plan.md 第7节
# TODO /stream：智能体流式输出（SSE）— plan.md 第7节