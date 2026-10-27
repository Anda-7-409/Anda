
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service, reminder_service, schedule_service

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
