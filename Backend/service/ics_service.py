
"""
ICS（iCalendar / RFC 5545）日历导出服务。

为什么用 ICS：它是日历互操作的行业标准，Apple 日历 / Google Calendar / Outlook /
手机系统日历都原生支持"导入单个 .ics 文件"或"长期订阅一个 text/calendar 源（feed）"，
无需自建推送通道即可获得系统级弹铃提醒（比网页轮询可靠）。

- 课程表（每周重复）→ 订阅 feed：每门课一个 VEVENT 带 RRULE:FREQ=WEEKLY，
  客户端订阅一次，课程增删改后下次刷新自动同步（UID 稳定 → 客户端按 UID 更新而非重复）。
- 单个提醒（一次性）→ 单事件 ICS 文件下载：VEVENT + VALARM，
  提醒提前量强制 >= MIN_LEAD_MIN(5 分钟)，事件展示时长也 >= 5 分钟。

订阅鉴权：日历 App 拉取订阅源时无法携带 Authorization 头，
因此用无状态 HMAC 派生 token（key=当前密码哈希）：
- 不落库、无需数据库迁移，URL 长期稳定可订阅；
- 改密码后 password_hash 变化 → 旧 token 自动失效（防密码泄露后日历被持续拉取）。
"""

import hashlib
import hmac
from datetime import datetime, time, timedelta

from Backend.config import FRONTEND_BASE_URL

# VALARM 最小提前量（分钟）：预约提醒必须至少提前 5 分钟响铃，留出准备时间
MIN_LEAD_MIN = 5
# VEVENT 展示时长（分钟）：事件本身持续 15 分钟，同样满足"提醒时长不小于 5 分钟"
EVENT_DUR_MIN = 15
# ICS 行折叠上限（RFC 5545 3.1 要求每行 <= 75 字节）
FOLD_BYTES = 75

BYDAY = {1: "MO", 2: "TU", 3: "WE", 4: "TH", 5: "FR", 6: "SA", 7: "SU"}

# ── 基础工具 ─────────────────────────────────────────────────────────────

def _esc(text) -> str:
    # RFC 5545 3.3.11：TEXT 值里的反斜杠/分号/逗号/换行必须转义
    return (str(text or "")
            .replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
            .replace("\r\n", "\\n").replace("\n", "\\n"))

def _fold(line: str) -> list:
    # 按 UTF-8 字节折行，续行以空格开头；避免把多字节中文字符折断
    raw = line.encode("utf-8")
    if len(raw) <= FOLD_BYTES:
        return [line]
    out, first, buf = [], True, bytearray()
    for ch in line:
        b = ch.encode("utf-8")
        limit = FOLD_BYTES if first else FOLD_BYTES - 1
        if len(buf) + len(b) > limit:
            out.append(buf.decode("utf-8", "ignore"))
            buf = bytearray(b" " + b)
            first = False
        else:
            buf.extend(b)
    if buf.strip():
        out.append(buf.decode("utf-8", "ignore"))
    return out

def _lines(rows) -> str:
    out = []
    for row in rows:
        out.extend(_fold(row) if isinstance(row, str) else _fold_all(row))
    return "\r\n".join(out) + "\r\n"

def _fold_all(rows) -> list:
    # 嵌套列表递归展开（如 VEVENT 块里内嵌 VALARM 列表）
    out = []
    for r in rows:
        out.extend(_fold_all(r) if isinstance(r, list) else _fold(r))
    return out

def _dt_local(dt: datetime) -> str:
    # 浮动本地时间（无 Z 后缀无 TZID）：Apple/Google/Outlook 都按用户日历时区解释，兼容性最好
    return dt.strftime("%Y%m%dT%H%M%S")

def _uid(kind: str, obj_id, user_id: int) -> str:
    # UID 稳定不变：订阅刷新时客户端按 UID 做"更新"，不会重复堆积
    return f"{kind}-{obj_id}-{user_id}@anda"

# ── 日历 token（无状态派生）─────────────────────────────────────────────

def calendar_token(user) -> str:
    mac = hmac.new(str(user.password_hash or "").encode("utf-8"),
                   f"calendar:{user.id}".encode("utf-8"), hashlib.sha256)
    return f"{user.id}.{mac.hexdigest()[:32]}"

def user_by_calendar_token(db, token: str):
    # 校验 token：拆出 user_id → 查用户 → 重算 HMAC 常量时间比对；无效返回 None
    s = str(token or "").split(".", 1)
    if len(s) != 2 or not s[0].isdigit():
        return None
    from Backend.models.user import User
    user = db.query(User).filter(User.id == int(s[0])).first()
    if not user or not hmac.compare_digest(calendar_token(user), str(token)):
        return None
    return user

def webcal_of(https_url: str) -> str:
    # webcal:// 是 http(s) 的别名 scheme，iOS/macOS/Outlook 点击可直接唤起日历 App
    return "webcal://" + https_url.split("://", 1)[1]

def reminder_ics_url(user, reminder_id: int) -> str:
    # 带 token 的绝对链接：AI 回答/浏览器直接点击都能下载，无需 Authorization 头
    return f"{FRONTEND_BASE_URL}/reminder/{reminder_id}/ics?token={calendar_token(user)}"

# ── 提醒时间解析（与 reminder_service._at 同语义）───────────────────────

def resolve_start(time_str: str, now: datetime):
    # "HH:MM" → 今天该时刻（已过则顺延明天）；"YYYY-MM-DD HH:MM" → 指定时刻；解析失败返回 None
    t = (time_str or "").strip()
    try:
        if ":" not in t:
            return None
        if len(t) > 5:
            return datetime.strptime(t, "%Y-%m-%d %H:%M")
        h, m = t.split(":")
        return now.replace(hour=int(h), minute=int(m), second=0, microsecond=0)
    except (ValueError, TypeError):
        return None

# ── 单个提醒 ICS（VEVENT + VALARM）──────────────────────────────────────

def _alarm(lead_min: int = MIN_LEAD_MIN) -> list:
    lead = max(MIN_LEAD_MIN, int(lead_min))   # 提前量下限 5 分钟，配置更短也按 5 分钟算
    return ["BEGIN:VALARM",
            f"TRIGGER:-PT{lead}M",
            "ACTION:DISPLAY",
            f"DESCRIPTION:{_esc('安答提醒：请留意以下事项')}",
            "END:VALARM"]

def build_reminder_ics(reminder: dict, user_id: int, lead_min: int = MIN_LEAD_MIN) -> str:
    now = datetime.now()
    start = resolve_start(reminder.get("reminder_time") or "", now)
    if not start:
        return ""
    end = start + timedelta(minutes=max(EVENT_DUR_MIN, lead_min))
    text = reminder.get("reminder_type") or "提醒"
    return _lines([
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Anda//Campus Assistant//CN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:安答提醒",
        ["BEGIN:VEVENT",
         f"UID:{_uid('reminder', reminder.get('id', 0), user_id)}",
         f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
         f"DTSTART:{_dt_local(start)}",
         f"DTEND:{_dt_local(end)}",
         f"SUMMARY:{_esc(text)}",
         f"DESCRIPTION:{_esc('来自安答的提醒：' + text)}",
         "SEQUENCE:0",
         _alarm(lead_min),
         "END:VEVENT"],
        "END:VCALENDAR",
    ])

def build_reminders_ics(reminders: list, user_id: int) -> str:
    # 全部带时间的提醒打包进一个 ICS（备份/批量导入用）；没时间的条目跳过
    now = datetime.now()
    rows = ["BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//Anda//Campus Assistant//CN", "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH", "X-WR-CALNAME:安答提醒"]
    count = 0
    for r in reminders:
        start = resolve_start(r.get("reminder_time") or "", now)
        if not start:
            continue
        text = r.get("reminder_type") or "提醒"
        rows.append([
            "BEGIN:VEVENT",
            f"UID:{_uid('reminder', r.get('id', 0), user_id)}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{_dt_local(start)}",
            f"DTEND:{_dt_local(start + timedelta(minutes=EVENT_DUR_MIN))}",
            f"SUMMARY:{_esc(text)}",
            "SEQUENCE:0",
            _alarm(),
            "END:VEVENT"])
        count += 1
    rows.append("END:VCALENDAR")
    return _lines(rows) if count else ""

# ── 课程表订阅 feed（RRULE 每周重复）────────────────────────────────────

def build_schedule_ics(courses: list, user_id: int) -> str:
    now = datetime.now()
    rows = ["BEGIN:VCALENDAR", "VERSION:2.0",
            "PRODID:-//Anda//Campus Assistant//CN", "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH", "X-WR-CALNAME:安答课表",
            "REFRESH-INTERVAL;VALUE=DURATION:PT12H",
            "X-PUBLISHED-TTL:PT12H"]
    # 时段去重：课表没有周次/单双周概念，同一 (weekday,节次区间) 出现多条记录是重复录入
    # （AI 抽取重试、用户重复添加都会造成），全部导出日历必重叠 → 按添加顺序只保留最早一条
    seen = set()
    for c in sorted(courses, key=lambda x: x.get("id", 0)):
        key = (c["weekday"], c["start_slot"], c["end_slot"])
        if key in seen:
            continue
        seen.add(key)
        # 节次→钟点：8:00 起每节 60 分钟、课长 45 分钟（与 routes/reminder.py due 逻辑一致）
        start_min = 8 * 60 + (c["start_slot"] - 1) * 60
        end_min = 8 * 60 + (c["end_slot"] - 1) * 60 + 45
        if start_min >= 24 * 60 or end_min >= 24 * 60:
            continue
        # 首次 DTSTART 取"本周该 weekday"（当天该时刻已过则推到下周），之后 RRULE 每周重复
        first_day = now.date() + timedelta(days=(c["weekday"] - now.isoweekday()) % 7)
        start = datetime.combine(first_day, time(0)) + timedelta(minutes=start_min)
        if start <= now:
            start += timedelta(days=7)
        end = start - timedelta(minutes=start_min) + timedelta(minutes=end_min)
        summary = c["name"] + (f"（{c['classroom']}）" if c.get("classroom") else "")
        desc = "教师：" + (c.get("teacher") or "未知") + "；来自安答课表订阅"
        rows.append([
            "BEGIN:VEVENT",
            f"UID:{_uid('course', c['id'], user_id)}",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{_dt_local(start)}",
            f"DTEND:{_dt_local(end)}",
            f"RRULE:FREQ=WEEKLY;BYDAY={BYDAY[c['weekday']]}",
            f"SUMMARY:{_esc(summary)}",
            f"LOCATION:{_esc(c.get('classroom') or '')}",
            f"DESCRIPTION:{_esc(desc)}",
            "SEQUENCE:0",
            _alarm(),
            "END:VEVENT"])
    rows.append("END:VCALENDAR")
    return _lines(rows)

# ── AI 工具：导出到系统日历 ─────────────────────────────────────────────

def calendar_export_tool(utterance: str, user_id: int, **_) -> dict:
    # 返回课表订阅链接（webcal + https）和提醒打包 ICS 下载链接
    from Backend.database import SessionLocal
    from Backend.models.user import User
    from Backend.service import schedule_service
    from Backend.models.reminder import Reminder
    with SessionLocal() as db:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"ok": False, "code": 30, "error": "用户不存在"}
        token = calendar_token(user)
        course_count = db.query(schedule_service.Course).filter(schedule_service.Course.user_id == user_id).count()
        reminder_count = db.query(Reminder).filter(Reminder.user_id == user_id, Reminder.reminder_time != "").count()
    https = f"{FRONTEND_BASE_URL}/schedule/ics.ics?token={token}"
    all_ics = f"{FRONTEND_BASE_URL}/reminder/all/ics?token={token}"
    return {
        "ok": True,
        "course_count": course_count,
        "reminder_count": reminder_count,
        "webcal_url": webcal_of(https),
        "https_url": https,
        "all_reminders_ics_url": all_ics,
        "howto": ("课程表订阅：手机/电脑日历 App → 添加订阅日历（Subscribed Calendar）→ 粘贴 webcal_url，"
                  "每周课程自动同步（约每12小时刷新）。"
                  "单个提醒：链接形如 /reminder/{提醒id}/ics?token=…，浏览器打开即下载 .ics 文件，导入日历后提前至少5分钟响铃。"),
    }
