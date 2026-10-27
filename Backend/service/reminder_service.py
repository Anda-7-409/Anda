
# reminder_service.py (提醒业务) 设置/查询/修改/删除/确认 + 到点提醒推送源；同时供路由层与 Agent 工具复用
import json
import re
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy.orm import Session

from AI import model_router
from Backend.database import SessionLocal
from Backend.models.reminder import Reminder
from Backend.service.schedule_service import WEEK_CN

DUE_WINDOW_MIN = 30   # 到点后 30 分钟内都算"该推送了"：错过整点才打开页面也能收到

def _to_dict(r: Reminder) -> dict:
    # 返回契约：与前端提醒卡片字段一致，前端零改动即可渲染
    return {
        "id": r.id,
        "reminder_type": r.reminder_type,
        "reminder_time": r.reminder_time or "",
        "is_done": r.is_done,
    }

def _list(db: Session, user_id: int) -> List[Reminder]:
    # 所有查询强制带 user_id 条件：只能看到自己的提醒（与 schedule/memo/upload 同思路）
    return db.query(Reminder).filter(Reminder.user_id == user_id).order_by(Reminder.reminder_time).all()

def _check_time(value: str) -> bool:
    # 两种合法格式："HH:MM"（今天） / "YYYY-MM-DD HH:MM"（指定日期）
    return bool(re.fullmatch(r"\d{1,2}:\d{2}", value)
                or re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}", value))

def set_reminder(db: Session, user_id: int, req) -> dict:
    text = (req.reminder_type or "").strip()
    time_str = (req.reminder_time or "").strip()
    if not text:
        return {"ok": False, "message": "提醒内容不能为空哦~"}
    if time_str and not _check_time(time_str):
        return {"ok": False, "message": "时间格式不对哦，应为 HH:MM 或 YYYY-MM-DD HH:MM"}
    r = Reminder(user_id=user_id, reminder_type=text, reminder_time=time_str)
    db.add(r)
    db.commit()
    db.refresh(r)
    return {"ok": True, "data": _to_dict(r)}

def get_reminders(db: Session, user_id: int) -> dict:
    return {"ok": True, "data": {"reminders": [_to_dict(r) for r in _list(db, user_id)]}}

def update_reminder(db: Session, user_id: int, reminder_id: int, req) -> dict:
    r = db.query(Reminder).filter(Reminder.id == reminder_id, Reminder.user_id == user_id).first()
    if not r:
        return {"ok": False, "message": "提醒不存在或不属于你哦~"}
    if req.reminder_type is not None:
        text = req.reminder_type.strip()
        if not text:
            return {"ok": False, "message": "提醒内容不能为空哦~"}
        r.reminder_type = text
    if req.reminder_time is not None:
        time_str = req.reminder_time.strip()
        if time_str and not _check_time(time_str):
            return {"ok": False, "message": "时间格式不对哦，应为 HH:MM 或 YYYY-MM-DD HH:MM"}
        r.reminder_time = time_str
    db.commit()
    db.refresh(r)
    return {"ok": True, "data": _to_dict(r)}

def delete_reminder(db: Session, user_id: int, reminder_id: int) -> dict:
    r = db.query(Reminder).filter(Reminder.id == reminder_id, Reminder.user_id == user_id).first()
    if not r:
        return {"ok": False, "message": "提醒不存在或不属于你哦~"}
    db.delete(r)
    db.commit()
    return {"ok": True, "data": {"id": reminder_id}}

def mark_done(db: Session, user_id: int, reminder_id: int, done: int) -> dict:
    # done/undo 共用一条逻辑：done=1 已确认，done=0 撤回确认
    r = db.query(Reminder).filter(Reminder.id == reminder_id, Reminder.user_id == user_id).first()
    if not r:
        return {"ok": False, "message": "提醒不存在或不属于你哦~"}
    r.is_done = done
    db.commit()
    return {"ok": True, "data": _to_dict(r)}

def _at(now: datetime, time_str: str) -> Optional[datetime]:
    # "HH:MM" → 今天此刻；"YYYY-MM-DD HH:MM" → 指定时刻；解析失败返回 None（跳过）
    try:
        if ":" not in time_str:
            return None
        if len(time_str) > 5:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        h, m = time_str.split(":")
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    except (ValueError, TypeError):
        return None

def due_list(db: Session, user_id: int) -> dict:
    # 主动推送数据源：未确认 + 已到点 + 未超 30 分钟窗口的提醒
    now = datetime.now()
    out = []
    for r in _list(db, user_id):
        if r.is_done:
            continue
        at = _at(now, r.reminder_time or "")
        if at and at <= now <= at + timedelta(minutes=DUE_WINDOW_MIN):
            out.append(_to_dict(r))
    return {"ok": True, "data": out}

# —— 自然语言设置提醒（与 schedule_add 同款方案B）：模型抽取 → 校验 → 写库 ——
REMIND_PROMPT = """你是提醒字段抽取器。把用户话术解析成一个 JSON 对象，只输出 JSON 本身，禁止代码块、禁止解释。
字段规则：

- "reminder_type"：提醒内容（字符串，必填，提炼成简洁一句，如"交高数作业"）

- "reminder_time"：提醒时间（字符串，必填）：
  - 用户说今天或只说钟点（如"8点""下午3点"）→ 输出 "HH:MM"（24小时制，下午3点=15:00）
  - 若该钟点已在当前时刻之前（今天已过去）→ 顺延到明天，输出 "YYYY-MM-DD HH:MM"（已过的时刻无法再提醒，语义上等于明天）
  - 用户说明天/后天/X天后 → 输出 "YYYY-MM-DD HH:MM"（按所给今天日期推算）
  - 用户说"N分钟后/X小时后/过X分钟" → 以所给当前时刻为准推算出 "YYYY-MM-DD HH:MM"（系统按分钟提醒，不足 1 分钟按 1 分钟算，"30秒后"按 1 分钟后处理）
缺少内容或时间时，只输出：{"error": "缺了什么就直说缺什么"}
示例1：
当前时刻：2026-10-24 23:30
用户话术：明早8点提醒我交高数作业
输出：{"reminder_type": "交高数作业", "reminder_time": "2026-10-25 08:00"}
示例2：
当前时刻：2026-10-24 23:30
用户话术：30秒后提醒我做下一版
输出：{"reminder_type": "做下一版", "reminder_time": "2026-10-24 23:31"}
示例3：
当前时刻：2026-10-24 16:35
用户话术：今天12:24叫我学数学
输出：{"reminder_type": "学数学", "reminder_time": "2026-10-25 12:24"}"""

def _parse_json(text: str) -> dict:
    # 容错：模型可能裹 ```json 代码块或加前后废话，截取首尾大括号之间再解析
    s = text.strip()
    if s.startswith("```"):
        s = s.strip("`")
        if s.startswith("json"):
            s = s[4:]
        s = s.strip()
    l, r = s.find("{"), s.rfind("}")
    if l == -1 or r <= l:
        return {}
    try:
        obj = json.loads(s[l:r + 1])
        return obj if isinstance(obj, dict) else {}
    except Exception:
        return {}

def set_tool(utterance: str, user_id: int, **_) -> dict:
    # orchestrator 以 fn(utterance=, user_id=) 调用，拿不到请求级 db → 自建会话
    now = datetime.now()
    messages = [
        {"role": "system", "content": REMIND_PROMPT},
        {"role": "user", "content":
            f"当前日期：{now.strftime('%Y-%m-%d')}（{WEEK_CN[now.isoweekday()]}），当前时刻：{now.strftime('%H:%M')}。用户话术：{utterance}"},
    ]
    text, provider = model_router.chat(messages)
    if not text:
        return {"ok": False, "error": "抽取模型暂不可用，稍后重试或走 POST /reminder/set 手动添加"}
    data = _parse_json(text)
    if not data:
        return {"ok": False, "error": "没听懂要提醒什么", "hint": "追问用户：提醒什么、几点"}
    if "error" in data:
        return {"ok": False, "error": str(data["error"]), "hint": "信息不全，向用户追问后再调用本工具"}
    time_str = str(data.get("reminder_time") or "").strip()
    if not time_str or not _check_time(time_str):
        return {"ok": False, "error": f"时间格式无法识别：{time_str or '空'}"}
    req = type("Req", (), {"reminder_type": str(data.get("reminder_type") or ""),
                           "reminder_time": time_str})()
    with SessionLocal() as db:
        result = set_reminder(db, user_id, req)
    if not result["ok"]:
        return {"ok": False, "error": result["message"]}
    return {"ok": True, "reminder": result["data"], "extracted_by": provider}

def query_tool(utterance: str, user_id: int, **_) -> dict:
    # Agent 工具入口：AI 答"我有什么提醒"时的数据源
    with SessionLocal() as db:
        reminders = [_to_dict(r) for r in _list(db, user_id)]
    pending = [r for r in reminders if not r["is_done"]]
    return {"count": len(pending), "reminders": pending, "confirmed": len(reminders) - len(pending)}
