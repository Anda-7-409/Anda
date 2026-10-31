
import json
from datetime import datetime
from types import SimpleNamespace
from typing import List, Optional

from sqlalchemy.orm import Session

from AI import model_router
from AI.model_router import NoModelError   # 模型全挂的降级分支要用，漏 import 会 NameError（这个跟头栽过一次 (＞﹏＜)）
from Backend.database import SessionLocal
from Backend.models.schedule import Course

WEEK_CN = {1: "周一", 2: "周二", 3: "周三", 4: "周四", 5: "周五", 6: "周六", 7: "周日"}

def _to_dict(c: Course) -> dict:
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
    q = db.query(Course).filter(Course.user_id == user_id)
    if weekday:
        q = q.filter(Course.weekday == weekday)
    return q.order_by(Course.weekday, Course.start_slot).all()

def today_courses(db: Session, user_id: int) -> dict:
    today = datetime.now().isoweekday() % 7 + 1  
    return {"ok": True, "data": [_to_dict(c) for c in _list(db, user_id, today)]}

def week_courses(db: Session, user_id: int) -> dict:
    return {"ok": True, "data": [_to_dict(c) for c in _list(db, user_id)]}

def add_course(db: Session, user_id: int, req) -> dict:
    if req.end_slot < req.start_slot:
        return {"ok": False,"code": 26, "message": "结束节次不能早于开始节次哦 (。•́︿•̀。) 时间不能倒流呀~"}
    name = req.name.strip()
    # 防重：同一用户同时段同课程名已存在 → 幂等返回既有记录，不再插入
    # （FC 抖动重复调用工具/用户重复添加会造出脏数据，导出日历就会出现同时间重叠事件，吃相很难看 (。•́︿•̀。)）
    exists = db.query(Course).filter(
        Course.user_id == user_id, Course.name == name,
        Course.weekday == req.weekday, Course.start_slot == req.start_slot,
        Course.end_slot == req.end_slot).first()
    if exists:
        return {"ok": True, "code": 0, "data": _to_dict(exists),
                "message": "这门课已经在课表里蹲着啦，就不重复添加了哦 (¬‿¬)"}
    course = Course(
        user_id=user_id,
        name=name,
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
        return {"ok": False,"code": 27, "message": "课程不存在，或者它不是你的哦 (´•̥ω•̥`)"}
    db.delete(course)
    db.commit()
    return {"ok": True, "data": {"id": course_id}}

def query_tool(utterance: str, user_id: int, **_) -> dict:
    weekday = None
    scope = "全周"
    if "明天" in utterance:
        weekday = datetime.now().isoweekday() % 7 + 1  
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


EXTRACT_PROMPT = """你是课表字段抽取器。把用户话术解析成一个 JSON 对象，只输出 JSON 本身，禁止代码块、禁止解释。
字段规则：
- "name"：课程名称（字符串，必填）
- "weekday"：星期几（整数，必填）：1=周一 2=周二 3=周三 4=周四 5=周五 6=周六 7=周日
- "start_slot"：开始节次（整数 1-12，必填）
- "end_slot"：结束节次（整数 1-12，不小于 start_slot；用户没说就等于 start_slot）
- 节次↔钟点换算（整点上课、每节45分钟）：8:00=第1节 9:00=第2节 10:00=第3节 11:00=第4节 12:00=第5节 13:00=第6节 14:00=第7节 15:00=第8节 16:00=第9节 17:00=第10节 18:00=第11节 19:00=第12节
- 用户给钟点（如"下午3:00""15:00""下午2:52"）→ 按上表换算成节次：下午/晚上几点先加12变成24小时制，再取最接近的整点节次（下午3:00=15:00→第8节；下午2:52=14:52≈15:00→第8节；"下午3点"同理）
- "classroom"：上课地点（字符串，没有则空字符串）
- "teacher"：教师（字符串，没有则空字符串）
缺少 name/weekday/start_slot 时，只输出：{"error": "缺了什么就直说缺什么"}
示例1：
用户话术：今天是周三(weekday=3)，明天是周四(weekday=4)。周四1-2节教南109来节高数，花老师教
输出：{"name": "高数", "weekday": 4, "start_slot": 1, "end_slot": 2, "classroom": "教南109", "teacher": "花老师"}
示例2：
用户话术：今天是周六(weekday=6)，明天是周日(weekday=7)。今天下午3:00有一堂数学课
输出：{"name": "数学", "weekday": 6, "start_slot": 8, "end_slot": 8}"""


def _parse_json(text: str) -> dict:
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


def add_tool(utterance: str, user_id: int, **_) -> dict:
    today = datetime.now().isoweekday()
    tomorrow = today % 7 + 1
    messages = [
        {"role": "system", "content": EXTRACT_PROMPT},
        {"role": "user", "content":
            f"今天是{WEEK_CN[today]}(weekday={today})，明天是{WEEK_CN[tomorrow]}(weekday={tomorrow})。用户话术：{utterance}"},
    ]
    try:
        msg, provider = model_router.chat("reasoning", messages)
        text = (msg or {}).get("content") or ""
    except NoModelError:
        return {"ok": False,"code": 12, "error": "抽取模型暂时打瞌睡了 (´・ω・`) 请稍后重试，或走手动添加接口"}
    data = _parse_json(text)
    if not data:
        return {"ok": False,"code": 13, "error": "没听懂要加哪门课呢 (´･ω･`)", "hint": "追问用户：课程名、星期几、第几节"}
    if "error" in data:
        return {"ok": False,"code": 14, "error": str(data["error"]), "hint": "信息不全，向用户追问后再调用本工具"}
    try:
        req = SimpleNamespace(
            name=str(data.get("name") or "").strip(),
            teacher=str(data.get("teacher") or "").strip(),
            classroom=str(data.get("classroom") or "").strip(),
            weekday=int(data["weekday"]),
            start_slot=int(data["start_slot"]),
            end_slot=int(data.get("end_slot") or data["start_slot"]),
        )
    except (KeyError, TypeError, ValueError):
        return {"ok": False,"code": 15, "error": "抽取结果字段有点奇怪，模型怕是已读乱回了 (°ㅂ°╬) 换个说法再试一次吧", "raw": str(data)[:200]}
    if not req.name:
        return {"ok": False,"code": 16, "error": "缺少课程名称哦 (。•́︿•̀。) 课程总得有个名字呀"}
    if not 1 <= req.weekday <= 7:
        return {"ok": False,"code": 17, "error": f"星期几超出范围：{req.weekday} (。•́︿•̀。) 一周只有 1-7 哦"}
    if not (1 <= req.start_slot <= 12 and 1 <= req.end_slot <= 12):
        return {"ok": False,"code": 28, "error": "节次需在 1-12 之间哦 (。•́︿•̀。) 一天最多十二节课呀"}
    if req.end_slot < req.start_slot:
        return {"ok": False,"code": 29, "error": "结束节次不能早于开始节次哦 (。•́︿•̀。) 时间不能倒流呀~"}
    with SessionLocal() as db:
        result = add_course(db, user_id, req)  
    if not result["ok"]:
        return {"ok": False, "error": result["message"]}
    start_min = 8 * 60 + (req.start_slot - 1) * 60
    end_min = 8 * 60 + (req.end_slot - 1) * 60 + 45
    return {
        "ok": True,
        "course": result["data"],
        "start_clock": f"{start_min // 60:02d}:{start_min % 60:02d}",
        "end_clock": f"{end_min // 60:02d}:{end_min % 60:02d}",
        "extracted_by": provider,
    }