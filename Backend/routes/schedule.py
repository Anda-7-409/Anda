from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.config import FRONTEND_BASE_URL
from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service, ics_service, schedule_service

router = APIRouter()

class CourseCreate(BaseModel):
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

@router.get("/ics/token")
def ics_token(user: User = Depends(auth_service.get_current_user)):
    # 登录态取订阅信息：token 由密码哈希无状态派生（改密码自动失效），不落库
    token = ics_service.calendar_token(user)
    https = f"{FRONTEND_BASE_URL}/schedule/ics.ics?token={token}"
    return _ok({
        "token": token,
        "https_url": https,
        "webcal_url": ics_service.webcal_of(https),
        "all_reminders_ics_url": f"{FRONTEND_BASE_URL}/reminder/all/ics?token={token}",
        "howto": "日历 App → 添加订阅日历 → 粘贴 webcal_url，每周课程自动同步",
    })

@router.get("/ics.ics")
def ics_feed(token: str = "", db: Session = Depends(get_db)):
    # 课程表订阅源：日历 App 定期拉取（无法带 Authorization 头，只能用 ?token= 鉴权——日历 App 不配合，只能惯着它 (。•́︿•̀。)）
    user = ics_service.user_by_calendar_token(db, token)
    if not user:
        return JSONResponse(status_code=401, content={"code": 1, "message": "订阅链接无效或已失效（改过密码需重新订阅）哦 (´•̥ω•̥`)"})
    body = ics_service.build_schedule_ics(schedule_service.week_courses(db, user.id)["data"], user.id)
    # inline：日历 App 直接读取 feed 内容；REFRESH-INTERVAL 已在 ICS 内声明
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": 'inline; filename="anda-schedule.ics"'})

@router.get("/today")
def get_today(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    return _ok(schedule_service.today_courses(db, user.id)["data"])

@router.get("/courses")
def get_courses(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
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
