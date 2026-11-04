# -*- coding: utf-8 -*-
"""judge.py — 实验三判分规则（先于实验冻结，改动即作废已测数据）

【课表抽取判分】
- 该课程判"对"的充分必要条件：课程名归一化后匹配 + weekday 相等
  + start_slot 相等 + end_slot 相等，四个字段全对才算对（end_slot 缺省时按 start_slot）；
- 课程名归一化：去所有空白、全角转半角、小写、去括号及其内容
  （"高等数学(一)"≈"高等数学"），然后双向包含即算名对（"高数"⊂"高等数学"算对，
  课表常写简称——此条为冻结口径，答辩被问直接引用）；
- 教室/教师只作辅助指标不参与"全对"判定：在名字与时间都配对的课程上，
  归一化后双向包含算对；GT 为空字符串则不计入分母；
- 配对为 1:1 贪心：每门 GT 课程至多消费一条抽取结果，防一条结果重复得分；
- 图片级"完全正确" = matched == gt_total 且 extra == 0。

【提醒指令判分】
- 内容（reminder_type）：包含 kp 中任一关键词（归一化后）即内容对；
- 时间（reminder_time）：与脚本按冻结规则现算的期望时刻比对（期望值依赖运行时刻，
  相对时间在评测时换算成绝对时刻，口径与线上 REMIND_PROMPT 完全一致）：
    clock    今天该钟点；已过 → 顺延明天（与提示词"已过时刻=明天"同口径），
             未顺延时接受 "HH:MM" 或完整日期两种写法，顺延后必须写完整日期；
    relative 今天+days 天的该钟点，days==0 时同 clock 口径；
    delta    当前时刻(截断到分钟)+minutes，允许 ±tolerance_min 分钟；
    absolute 固定日期+钟点；
    weekday  严格晚于今天的下一个"周X"的该钟点（信息来自提示词里注入的今天周几）；
    fuzzy    期望系统输出 {"error": ...} 追问而不是编造时间；返回了 reminder_time
             即判 FAIL（error_type=hallucination，这是宝贵的错误案例素材）；
- 时间格式必须为 "HH:MM" 或 "YYYY-MM-DD HH:MM"（与线上 _check_time 一致）。
"""
import re
from datetime import datetime, timedelta

FULL_FMT = "%Y-%m-%d %H:%M"


# ---------- 通用归一化 ----------
def norm_text(s: str) -> str:
    s = (s or "").strip().lower()
    table = str.maketrans("（）【】，。；：！？", "()[],.;:!?")
    s = s.translate(table)
    s = re.sub(r"\([^)]*\)|\[[^\]]*\]", "", s)   # 去括号及内容
    s = re.sub(r"\s+", "", s)
    return s


def name_match(gt: str, out: str) -> bool:
    g, o = norm_text(gt), norm_text(out)
    if not g or not o:
        return False
    return g in o or o in g


def contains_match(gt: str, out: str) -> bool:
    g, o = norm_text(gt), norm_text(out)
    if not g:
        return True    # GT 为空不计入分母
    return bool(o) and (g in o or o in g)


# ---------- 课表抽取判分 ----------
def judge_extract(gt_courses: list, out_courses: list) -> dict:
    """返回 {gt_total, out_total, matched, extra, missed, course_acc, image_exact,
             room_acc, teacher_acc, missed_detail}"""
    gt_total, out_total = len(gt_courses), len(out_courses)
    used = [False] * out_total
    matched = room_hit = room_den = tea_hit = tea_den = 0
    missed_detail = []
    for gt in gt_courses:
        try:
            g_key = (norm_text(str(gt.get("name", ""))), int(gt["weekday"]),
                     int(gt["start_slot"]),
                     int(gt.get("end_slot") or gt["start_slot"]))
        except (KeyError, TypeError, ValueError):
            missed_detail.append(f"GT字段异常:{gt}")
            continue
        hit = -1
        for j, out in enumerate(out_courses):
            if used[j]:
                continue
            try:
                o_key = (norm_text(str(out.get("name", ""))), int(out["weekday"]),
                         int(out["start_slot"]),
                         int(out.get("end_slot") or out["start_slot"]))
            except (KeyError, TypeError, ValueError):
                continue
            if o_key == g_key:
                hit = j
                break
        if hit >= 0:
            used[hit] = True
            matched += 1
            # 辅助字段：在课程主体配对成功的基础上统计
            o = out_courses[hit]
            if str(gt.get("classroom", "")).strip():
                room_den += 1
                room_hit += contains_match(str(gt.get("classroom", "")),
                                           str(o.get("classroom", "")))
            if str(gt.get("teacher", "")).strip():
                tea_den += 1
                tea_hit += contains_match(str(gt.get("teacher", "")),
                                          str(o.get("teacher", "")))
        else:
            missed_detail.append(
                f"{gt.get('name', '?')} 周{gt.get('weekday', '?')} "
                f"{gt.get('start_slot', '?')}-{gt.get('end_slot', '?')}节")
    extra = out_total - sum(used)
    course_acc = matched / gt_total if gt_total else 0.0
    return {
        "gt_total": gt_total, "out_total": out_total, "matched": matched,
        "extra": extra, "missed": gt_total - matched,
        "course_acc": round(course_acc, 4),
        "image_exact": int(matched == gt_total and extra == 0 and gt_total > 0),
        "room_acc": round(room_hit / room_den, 4) if room_den else None,
        "teacher_acc": round(tea_hit / tea_den, 4) if tea_den else None,
        "missed_detail": "; ".join(missed_detail)[:180],
    }


def parse_courses_json(text: str) -> list:
    """从视觉模型回答里抠出课程 JSON 数组（容错 ```json 围栏与前后废话）"""
    s = (text or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```[a-zA-Z]*", "", s).strip("`").strip()
    l, r = s.find("["), s.rfind("]")
    if l == -1 or r <= l:
        # 退化：模型输出 {"courses": [...]} 单对象形态
        l2, r2 = s.find("{"), s.rfind("}")
        if l2 != -1 and r2 > l2:
            try:
                obj = json_loads(s[l2:r2 + 1])
                if isinstance(obj, dict) and isinstance(obj.get("courses"), list):
                    return obj["courses"]
            except Exception:
                pass
        return []
    import json
    try:
        arr = json.loads(s[l:r + 1])
        return arr if isinstance(arr, list) else []
    except Exception:
        return []


def json_loads(s: str):
    import json
    return json.loads(s)


# ---------- 提醒指令判分 ----------
def expected_time(case: dict, now: datetime):
    """按冻结口径现算期望时刻。返回 (target_datetime, accept_hhmm_only:bool)"""
    kind = case.get("kind")
    clock = str(case.get("clock") or "00:00")
    h, m = (int(x) for x in clock.split(":"))
    if kind == "clock":
        target = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if target <= now:   # 已过时刻 → 顺延明天（与线上提示词同口径）
            return target + timedelta(days=1), False
        return target, True
    if kind == "relative":
        target = (now + timedelta(days=int(case.get("days", 0)))
                  ).replace(hour=h, minute=m, second=0, microsecond=0)
        return target, int(case.get("days", 0)) == 0 and target > now
    if kind == "delta":
        base = now.replace(second=0, microsecond=0)
        return base + timedelta(minutes=int(case.get("minutes", 0))), False
    if kind == "absolute":
        d = datetime.strptime(str(case["date"]), "%Y-%m-%d")
        return d.replace(hour=h, minute=m), False
    if kind == "weekday":
        # 严格晚于今天的下一个周X（今天不算；信息来自提示词注入的今天周几）
        d = now.date() + timedelta(days=1)
        while d.isoweekday() != int(case["weekday"]):
            d += timedelta(days=1)
        return datetime(d.year, d.month, d.day, h, m), False
    raise ValueError(f"unknown kind {kind}")


def judge_reminder(case: dict, data: dict, now: datetime) -> dict:
    """data 为模型解析出的 JSON（可能含 error 键）。返回判分明细。"""
    kind = case.get("kind")
    out = {"type_ok": None, "time_ok": None, "pass": False, "error_type": "none"}
    if kind == "fuzzy":
        if "error" in data:   # 期望追问，不编造
            out["pass"] = True
            out["type_ok"] = None
            out["time_ok"] = None
        else:
            out["error_type"] = "hallucination"   # 模糊表达却编出了时间
        return out
    if "error" in data or not data:
        out["error_type"] = "abstain"   # 该答没答（信息明明充足却追问）
        return out
    # 内容
    rtype = str(data.get("reminder_type") or "")
    out["type_ok"] = int(any(norm_text(k) in norm_text(rtype)
                             for k in case.get("kp", []) if k))
    # 时间
    got = str(data.get("reminder_time") or "").strip()
    try:
        target, accept_hhmm = expected_time(case, now)
    except (ValueError, KeyError):
        out["error_type"] = "case_error"
        return out
    tol = int(case.get("tolerance_min", 0))
    ok_time = False
    parsed = None
    if re.fullmatch(r"\d{1,2}:\d{2}", got):
        if accept_hhmm:
            hh, mm = (int(x) for x in got.split(":"))
            parsed = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}", got):
        try:
            parsed = datetime.strptime(got, FULL_FMT)
        except ValueError:
            parsed = None
    if parsed is not None:
        diff = abs((parsed - target).total_seconds()) / 60
        ok_time = diff <= tol
    out["time_ok"] = int(ok_time)
    out["expected_time"] = target.strftime(FULL_FMT)
    out["got_time"] = got
    out["pass"] = out["type_ok"] == 1 and ok_time
    if not out["pass"] and out["error_type"] == "none":
        out["error_type"] = "time_wrong" if not ok_time else "type_wrong"
    return out
