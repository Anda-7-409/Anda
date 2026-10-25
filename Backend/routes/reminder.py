
# reminder.py (提醒路由) 对应 plan.md /reminder：设置/查询/修改/删除/确认/取消，外加 /due 主动推送数据源

# 身份统一走 Authorization: Bearer <token>（plan.md 认证说明：除 /auth/* 外所有接口带 Authorization）
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
    # 入口校验：内容非空 ≤200 字；时间格式（HH:MM / YYYY-MM-DD HH:MM）在 service 层正则校验
    reminder_type: str = Field(..., min_length=1, max_length=200)
    reminder_time: str = Field(default="", max_length=32)

class ReminderUpdate(BaseModel):
    # 修改接口：字段可选，只改传了的
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
    # 右栏"提醒"面板数据源：data:{reminders}（plan.md 契约）
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
    # 确认提醒：is_done=1
    result = reminder_service.mark_done(db, user.id, reminder_id, 1)
    if not result["ok"]:
        return _fail(result["message"], status=404)
    return _ok(result["data"])

@router.post("/{reminder_id}/undo")
def undo_reminder(reminder_id: int, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    # 取消确认：is_done=0，回到待提醒
    result = reminder_service.mark_done(db, user.id, reminder_id, 0)
    if not result["ok"]:
        return _fail(result["message"], status=404)
    return _ok(result["data"])

@router.get("/due")
def due_reminders(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    # 主动提醒数据源：前端每 30s 轮询；除 reminder 表到点提醒外，还合并今天的课表 → 课前 10 分钟网页版提醒
    out = reminder_service.due_list(db, user.id)["data"]
    PRE_CLASS_MIN = 10   # 提前 10 分钟（plan.md 场景创新点：每节课前主动提醒）
    now = datetime.now()
    for c in schedule_service._list(db, user.id, now.isoweekday()):
        # 时刻表：第 1 节 8:00 上课、8:45 下课，之后每节 +60 分钟（与 skill/system.py 共用同一约定）
        start_min = 8 * 60 + (c.start_slot - 1) * 60
        end_min = 8 * 60 + (c.end_slot - 1) * 60 + 45
        if start_min >= 24 * 60 or end_min >= 24 * 60:
            continue   # 防御：节次异常超范围时跳过，不拖挂整个接口
        start = now.replace(hour=start_min // 60, minute=start_min % 60, second=0, microsecond=0)
        if not (start - timedelta(minutes=PRE_CLASS_MIN) <= now <= start):
            continue   # 只在「课前10分钟～上课」窗口内返回：页面没开就不弹（不补打扰）
        out.append({
            "id": f"c-{now:%Y%m%d}-{c.id}",   # 带日期：同一节课明天重新触发；前端 firedReminders 按此去重
            "reminder_type": f"上课：{c.name}" + (f"（{c.classroom}）" if c.classroom else ""),
            "reminder_time": f"{start_min // 60:02d}:{start_min % 60:02d}",
            "is_done": 0,
        })
    return _ok(out)
