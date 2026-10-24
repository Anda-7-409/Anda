# schedule_service.py (课表业务) 今日/全周查询、手动增删；同一套业务同时供路由层与 Agent 工具复用
from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session

from Backend.database import SessionLocal
from Backend.models.schedule import Course

WEEK_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}

def _to_dict(c: Course) -> dict:
    # 返回契约：与前端日程卡片字段一致，前端零改动即可渲染
    return {
        "id": c.id,
        "name": c.name,
        "teacher": c.teacher or "",
        "classroom": c.classroom or "",
        "weekday": c.weekday,
        "start_slot": c.start_slot,
        "end_slot": c.end_slot,
    }

def _list(db: Session, user_id: int, weekday: Optional[int] = None) -> List[Course]:
    # 所有查询强制带 user_id 条件：只能看到自己的课（与 upload 权限隔离同思路）
    q = db.query(Course).filter(Course.user_id == user_id)
    if weekday:
        q = q.filter(Course.weekday == weekday)
    return q.order_by(Course.weekday, Course.start_slot).all()

def today_courses(db: Session, user_id: int) -> dict:
    today = datetime.now().isoweekday()  # 1=周一 … 7=周日
    return {"ok": True, "data": [_to_dict(c) for c in _list(db, user_id, today)]}

def week_courses(db: Session, user_id: int) -> dict:
    return {"ok": True, "data": [_to_dict(c) for c in _list(db, user_id)]}

def add_course(db: Session, user_id: int, req) -> dict:
    # 星期/节次范围由 Pydantic 入口校验（1-7 / 1-12），这里只做业务级检查
    if req.end_slot < req.start_slot:
        return {"ok": False, "message": "结束节次不能早于开始节次哦~ ?-?"}
    course = Course(
        user_id=user_id,
        name=req.name.strip(),
        teacher=(req.teacher or "").strip(),
        classroom=(req.classroom or "").strip(),
        weekday=req.weekday,
        start_slot=req.start_slot,
        end_slot=req.end_slot,
    )
    db.add(course)
    db.commit()
    db.refresh(course)
    return {"ok": True, "data": _to_dict(course)}

def delete_course(db: Session, user_id: int, course_id: int) -> dict:
    course = db.query(Course).filter(Course.id == course_id, Course.user_id == user_id).first()
    if not course:
        return {"ok": False, "message": "课程不存在或不属于你哦~"}
    db.delete(course)
    db.commit()
    return {"ok": True, "data": {"id": course_id}}

def query_tool(utterance: str, user_id: int) -> dict:
    # Agent 工具入口：orchestrator 以 fn(utterance=, user_id=) 调用，拿不到请求级 db → 自建会话
    # 时间意图解析：明天/今天/周X/星期X → 具体 weekday；无时间词 → 返回全周
    weekday = None
    scope = "全周"
    if "明天" in utterance:
        weekday = datetime.now().isoweekday() % 7 + 1   # 周日(7)自动回到周一(1)
        scope = f"明天({WEEK_CN[weekday]})"
    elif "今天" in utterance or "今日" in utterance:
        weekday = datetime.now().isoweekday()
        scope = f"今天({WEEK_CN[weekday]})"
    else:
        for num, cn in WEEK_CN.items():
            if cn in utterance or f"星期{cn[-1]}" in utterance:
                weekday = num
                scope = cn
                break
    with SessionLocal() as db:
        courses = [_to_dict(c) for c in _list(db, user_id, weekday)]
    return {"scope": scope, "count": len(courses), "courses": courses}