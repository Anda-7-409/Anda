
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service, ics_service, reminder_service, schedule_service

router = APIRouter()

class ReminderSet(BaseModel):
    reminder_type: str = Field(..., min_length=1, max_length=200)
    reminder_time: str = Field(default="", max_length=32)

class ReminderUpdate(BaseModel):
    reminder_type: Optional[str] = Field(default=None, min_length=1, max_length=200)
    reminder_time: Optional[str] = Field(default=None, max_length=32)

def _ok(data):
    return {"code": 0, "message": "ok", "data": data}

def _fail(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"code": 1, "message": message, "data": None})

def _user_from_bearer_or_query(db: Session, authorization: Optional[str], token: str) -> Optional[User]:
    # ICS 下载支持两种鉴权：前端 fetch 带 Bearer；浏览器/日历 App 直链用 ?token=（日历 token）
    if authorization and authorization.startswith("Bearer "):
        try:
            return auth_service.get_current_user(authorization=authorization, db=db)
        except Exception:
            return None
    return ics_service.user_by_calendar_token(db, token)

def _ics_response(body: str, filename: str) -> Response:
    # text/calendar + attachment：浏览器直接下载 .ics，双击可导入日历 App
    return Response(body, media_type="text/calendar; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})

@router.get("/all/ics")
def all_reminders_ics(authorization: Optional[str] = Header(default=None),
                      token: str = "", db: Session = Depends(get_db)):
    # 全部提醒打包成一个 ICS（备份/批量导入）；注意必须注册在 /{reminder_id}/ics 之前，否则 "all" 会先被动态路由吃掉
    user = _user_from_bearer_or_query(db, authorization, token)
    if not user:
        return JSONResponse(status_code=401, content={"code": 1, "message": "登录凭证无效哦~"})
    body = ics_service.build_reminders_ics(
        [reminder_service._to_dict(r) for r in reminder_service._list(db, user.id)], user.id)
    if not body:
        return JSONResponse(status_code=400, content={"code": 1, "message": "还没有带时间的提醒可以导出哦~"})
    return _ics_response(body, "anda-reminders.ics")

@router.get("/{reminder_id}/ics")
def reminder_ics(reminder_id: int, authorization: Optional[str] = Header(default=None),
                 token: str = "", db: Session = Depends(get_db)):
    # 单个提醒 → ICS 文件下载（VEVENT + VALARM，提前量 >= 5 分钟）
    user = _user_from_bearer_or_query(db, authorization, token)
    if not user:
        return JSONResponse(status_code=401, content={"code": 1, "message": "登录凭证无效哦~"})
    r = db.query(reminder_service.Reminder).filter(
        reminder_service.Reminder.id == reminder_id, reminder_service.Reminder.user_id == user.id).first()
    if not r:
        return JSONResponse(status_code=404, content={"code": 1, "message": "提醒不存在或不属于你哦~"})
    body = ics_service.build_reminder_ics(reminder_service._to_dict(r), user.id)
    if not body:
        return JSONResponse(status_code=400, content={"code": 1, "message": "该提醒没有有效时间，无法生成日历事件哦~"})
    return _ics_response(body, f"reminder-{reminder_id}.ics")

@router.post("/set")
def set_reminder(req: ReminderSet, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = reminder_service.set_reminder(db, user.id, req)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["data"])

@router.get("/get")
def get_reminders(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    return _ok(reminder_service.get_reminders(db, user.id)["data"])

@router.put("/{reminder_id}")
def update_reminder(reminder_id: int, req: ReminderUpdate, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = reminder_service.update_reminder(db, user.id, reminder_id, req)
    if not result["ok"]:
        return _fail(result["message"], status=404 if "不存在" in result["message"] else 400)
    return _ok(result["data"])

@router.delete("/{reminder_id}")
def delete_reminder(reminder_id: int, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = reminder_service.delete_reminder(db, user.id, reminder_id)
    if not result["ok"]:
        return _fail(result["message"], status=404 if "不存在" in result["message"] else 400)
    return _ok(result["data"])

@router.post("/{reminder_id}/done")
def done_reminder(reminder_id: int, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = reminder_service.mark_done(db, user.id, reminder_id, 1)
    if not result["ok"]:
        return _fail(result["message"], status=404)
    return _ok(result["data"])

@router.post("/{reminder_id}/undo")
def undo_reminder(reminder_id: int, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = reminder_service.mark_done(db, user.id, reminder_id, 0)
    if not result["ok"]:
        return _fail(result["message"], status=404)
    return _ok(result["data"])

@router.get("/due")
def due_reminders(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    out = reminder_service.due_list(db, user.id)["data"]
    PRE_CLASS_MIN = 10   
    now = datetime.now()
    for c in schedule_service._list(db, user.id, now.isoweekday()):
        start_min = 8 * 60 + (c.start_slot - 1) * 60
        end_min = 8 * 60 + (c.end_slot - 1) * 60 + 45
        if start_min >= 24 * 60 or end_min >= 24 * 60:
            continue   
        start = now.replace(hour=start_min // 60, minute=start_min % 60, second=0, microsecond=0)
        if not (start - timedelta(minutes=PRE_CLASS_MIN) <= now <= start):
            continue   
        out.append({
            "id": f"c-{now:%Y%m%d}-{c.id}",   
            "reminder_type": f"上课：{c.name}" + (f"（{c.classroom}）" if c.classroom else ""),
            "reminder_time": f"{start_min // 60:02d}:{start_min % 60:02d}",
            "is_done": 0,
        })
    return _ok(out)
