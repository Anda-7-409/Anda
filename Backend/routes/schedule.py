# schedule.py (课表路由) 对应 plan.md /schedule：今日课表、全周查询、手动增删（图片导入待OCR接入）
# 身份统一走 Authorization: Bearer <token>（plan.md 认证说明：除 /auth/* 外所有接口带 Authorization），
# 不再按 token_id 入参——与 upload / agent 保持同一套登录态
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service, schedule_service

router = APIRouter()

class CourseCreate(BaseModel):
    # 参数校验在入口自动完成：名称非空 1-64 字，星期 1-7，节次 1-12
    name: str = Field(..., min_length=1, max_length=64)
    teacher: str = ""
    classroom: str = ""
    weekday: int = Field(..., ge=1, le=7)
    start_slot: int = Field(..., ge=1, le=12)
    end_slot: int = Field(..., ge=1, le=12)

def _ok(data):
    return {"code": 0, "message": "ok", "data": data}

def _fail(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"code": 1, "message": message, "data": None})

@router.get("/today")
def get_today(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    # 右栏"今日日程"数据源：按服务器当天星期过滤
    return _ok(schedule_service.today_courses(db, user.id)["data"])

@router.get("/courses")
def get_courses(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    # 全周课表（按星期+节次排序）
    return _ok(schedule_service.week_courses(db, user.id)["data"])

@router.post("/courses")
def add_course(req: CourseCreate, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = schedule_service.add_course(db, user.id, req)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["data"])

@router.delete("/courses/{course_id}")
def delete_course(course_id: int, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = schedule_service.delete_course(db, user.id, course_id)
    if not result["ok"]:
        return _fail(result["message"], status=404 if "不存在" in result["message"] else 400)
    return _ok(result["data"])