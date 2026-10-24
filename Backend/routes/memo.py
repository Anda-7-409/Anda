
# memo.py (备忘录路由) 对应今日日程"+"：列表/添加/删除（AI 读取走 Agent 工具 memo_list）

# 身份统一走 Authorization: Bearer <token>（plan.md 认证说明：除 /auth/* 外所有接口带 Authorization）
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service, memo_service

router = APIRouter()

class MemoCreate(BaseModel):
    # 参数校验在入口自动完成：内容非空、最长 200 字
    content: str = Field(..., min_length=1, max_length=200)

def _ok(data):
    return {"code": 0, "message": "ok", "data": data}

def _fail(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"code": 1, "message": message, "data": None})

@router.get("/")
def get_memos(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    # 右栏"今日日程"备忘录数据源（与课程卡片混排在同一列表）
    return _ok(memo_service.list_memos(db, user.id)["data"])

@router.post("/")
def add_memo(req: MemoCreate, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = memo_service.add_memo(db, user.id, req.content)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["data"])

@router.delete("/{memo_id}")
def delete_memo(memo_id: int, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = memo_service.delete_memo(db, user.id, memo_id)
    if not result["ok"]:
        return _fail(result["message"], status=404 if "不存在" in result["message"] else 400)
    return _ok(result["data"])
