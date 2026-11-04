# -*- coding: utf-8 -*-
"""run_eval.py — 实验三主评测：抽取准确率（课表图片 × 视觉链 + 提醒指令 × 推理链）

被测链路与线上一致：
  - extract 模式：need/ 里的课表图片 → base64 视觉消息（与 tool/image_understand.py
    同构）→ model_router.chat("vision")（glm-4.6V-Flash → DeepSeek-OCR → Qwen3.5-4B 滑链）
    → 抽出课程 JSON 数组 → judge.judge_extract 按"课程名/星期/节次全对才算对"判分；
  - reminder 模式：cases/reminder_cases.json 的 20 条指令 → 与线上
    reminder_service.set_tool 完全相同的 REMIND_PROMPT + reasoning 链（不写数据库）
    → judge.judge_reminder 按内容+时间双指标判分，模糊表达期望追问而非编造。

判分规则先于实验冻结（judge.py），改动即作废已测数据。
用法：
  python test/Test3/run_eval.py --mode all                 # 全量（需先填好 extract_gt.json）
  python test/Test3/run_eval.py --mode extract --limit 3   # 前 3 张冒烟
  python test/Test3/run_eval.py --mode reminder            # 20 条提醒指令
  python test/Test3/run_eval.py --mode extract --gt test/Test3/cases/smoke_gt.json  # 样例图冒烟
"""
import argparse
import base64
import csv
import os
import sys
import time
from datetime import datetime
from pathlib import Path

TEST3_DIR = Path(__file__).parent
ROOT = TEST3_DIR.parent.parent
sys.path.insert(0, str(TEST3_DIR))
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from judge import judge_extract, judge_reminder, parse_courses_json  # noqa: E402

MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
        ".webp": "image/webp", ".bmp": "image/bmp"}

EXTRACT_CSV_FIELDS = ["image_id", "tag", "round", "provider", "ok", "gt_total",
                      "out_total", "matched", "extra", "missed", "course_acc",
                      "image_exact", "room_acc", "teacher_acc", "latency_s",
                      "error_type", "missed_detail", "raw_preview"]
REMINDER_CSV_FIELDS = ["case_id", "kind", "round", "provider", "ok", "pass",
                       "type_ok", "time_ok", "expected_time", "got_time",
                       "latency_s", "error_type", "raw_preview"]

# 冻结的课表抽取问法（与判分规则同批冻结；线上用户可自由问，评测统一用此问法保证可比）
EXTRACT_QUESTION = """请把这张课表图片里的全部课程整理成 JSON 数组输出，只输出 JSON 本身，禁止解释、禁止代码块。每门课一个对象，字段：
{"name": "课程名", "weekday": 1到7(1=周一), "start_slot": 1到12, "end_slot": 1到12, "classroom": "教室，没有则空字符串", "teacher": "教师，没有则空字符串"}
要求：
- 节次以图片中的节次列/行号为准；连堂课写成一个对象（start_slot 与 end_slot 不同）；单节课 end_slot 等于 start_slot
- 若图片用钟点表示时间，按 8:00=第1节、每节45分钟换算（14:00=第7节，15:00=第8节）
- 星期列 1=周一 … 7=周日；单周/双周课程按全周（每周都上）计算
- 不要遗漏任何一门课，不要编造图片里不存在的课程"""


def log(msg: str):
    print(msg, flush=True)


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def write_csv(out_csv: Path, fields, rows):
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    log(f"已写入：{out_csv}（{len(rows)} 行）")


# ---------- extract 模式 ----------
def run_extract(args) -> list:
    import json
    from AI import model_router
    gt_path = Path(args.gt) if args.gt else TEST3_DIR / "cases" / "extract_gt.json"
    gt = json.loads(gt_path.read_text("utf-8"))
    need = TEST3_DIR / "need"
    rows = []
    entries = sorted(gt.items())[:args.limit] if args.limit else sorted(gt.items())

    # 预检：图片在不在、真值填没填
    todo = []
    for fname, meta in entries:
        img = need / fname
        if not img.is_file():
            log(f"[跳过] {fname}：need/ 里找不到这张图")
            continue
        courses = meta.get("courses") or []
        if not courses:
            log(f"[跳过] {fname}：extract_gt.json 里还没填真值 courses")
            continue
        todo.append((fname, img, meta, courses))
    if not todo:
        log("[extract] 没有可评测的图片（need/ 放图 + extract_gt.json 填真值后再跑）")
        return []
    log(f"=== extract：{len(todo)} 张课表 × {args.rounds} 轮 ===")

    for fname, img, meta, gt_courses in todo:
        b64 = base64.b64encode(img.read_bytes()).decode()
        mime = MIME.get(img.suffix.lower(), "image/jpeg")
        messages = [{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": EXTRACT_QUESTION},
        ]}]
        for rnd in range(1, args.rounds + 1):
            t0 = time.perf_counter()
            provider, err = "", "none"
            out_courses, raw = [], ""
            try:
                msg, provider = model_router.chat("vision", messages)
                raw = (msg or {}).get("content") or ""
                out_courses = parse_courses_json(raw)
                if not out_courses:
                    err = "parse_fail"
            except Exception as e:   # noqa: BLE001
                err = f"model_fail:{type(e).__name__}"
                raw = str(e)[:150]
            latency = round(time.perf_counter() - t0, 3)
            j = judge_extract(gt_courses, out_courses)
            rows.append({
                "image_id": Path(fname).stem, "tag": meta.get("tag", ""), "round": rnd,
                "provider": provider, "ok": int(err == "none"),
                "gt_total": j["gt_total"], "out_total": j["out_total"],
                "matched": j["matched"], "extra": j["extra"], "missed": j["missed"],
                "course_acc": j["course_acc"], "image_exact": j["image_exact"],
                "room_acc": "" if j["room_acc"] is None else j["room_acc"],
                "teacher_acc": "" if j["teacher_acc"] is None else j["teacher_acc"],
                "latency_s": latency, "error_type": err,
                "missed_detail": j["missed_detail"],
                "raw_preview": raw[:200].replace("\n", " "),
            })
            log(f"  [{Path(fname).stem}] r{rnd} ok={err == 'none'} "
                f"{j['matched']}/{j['gt_total']} 门全对, 多检 {j['extra']}, "
                f"course_acc={j['course_acc']:.2f} {provider} {latency:.1f}s"
                + (f" err={err}" if err != "none" else ""))
    return rows


# ---------- reminder 模式 ----------
def run_reminder(args) -> list:
    import json
    from datetime import datetime as _dt
    from AI import model_router
    from Backend.service.reminder_service import REMIND_PROMPT, _parse_json
    cases = json.loads((TEST3_DIR / "cases" / "reminder_cases.json").read_text("utf-8"))
    items = sorted(cases.items())
    if args.limit:
        items = items[:args.limit]
    log(f"=== reminder：{len(items)} 条指令 × {args.rounds} 轮 ===")
    rows = []
    for cid, case in items:
        for rnd in range(1, args.rounds + 1):
            now = datetime.now()
            week_cn = "一二三四五六日"[now.isoweekday() - 1]
            messages = [
                {"role": "system", "content": REMIND_PROMPT},
                {"role": "user", "content":
                    f"当前日期：{now.strftime('%Y-%m-%d')}（周{week_cn}），"
                    f"当前时刻：{now.strftime('%H:%M')}。用户话术：{case['utterance']}"},
            ]
            t0 = time.perf_counter()
            provider, raw, data = "", "", {}
            err = "none"
            try:
                msg, provider = model_router.chat("reasoning", messages)
                raw = (msg or {}).get("content") or ""
                data = _parse_json(raw)
                if not data:
                    err = "parse_fail"
            except Exception as e:   # noqa: BLE001
                err = f"model_fail:{type(e).__name__}"
                raw = str(e)[:150]
            latency = round(time.perf_counter() - t0, 3)
            j = judge_reminder(case, data, now)
            rows.append({
                "case_id": cid, "kind": case["kind"], "round": rnd,
                "provider": provider, "ok": int(err == "none"),
                "pass": int(j["pass"]), "type_ok": "" if j["type_ok"] is None else j["type_ok"],
                "time_ok": "" if j["time_ok"] is None else j["time_ok"],
                "expected_time": j.get("expected_time", ""),
                "got_time": j.get("got_time", ""),
                "latency_s": latency, "error_type": err if err != "none" else j["error_type"],
                "raw_preview": raw[:200].replace("\n", " "),
            })
            mark = "PASS" if j["pass"] else "FAIL"
            log(f"  [{cid}|{case['kind']}] r{rnd} {mark} "
                f"type={j['type_ok']} time={j['time_ok']} "
                f"期望 {j.get('expected_time', '(期望追问)')} 实得 {j.get('got_time', '-')} "
                f"{provider} {latency:.1f}s"
                + (f" err={rows[-1]['error_type']}" if rows[-1]['error_type'] != 'none' else ""))
    return rows


def main():
    ap = argparse.ArgumentParser(description="实验三：抽取准确率评测（课表图片 + 提醒指令）")
    ap.add_argument("--mode", required=True, choices=("extract", "reminder", "all"))
    ap.add_argument("--rounds", type=int, default=1, help="每条用例轮次，默认 1")
    ap.add_argument("--limit", type=int, default=0, help="只取前 N 条（冒烟用）")
    ap.add_argument("--gt", default="", help="课表真值 JSON 路径（默认 cases/extract_gt.json）")
    ap.add_argument("--out", default="", help="输出目录，默认 test/Test3/results")
    args = ap.parse_args()

    load_env()
    out_dir = Path(args.out) if args.out else TEST3_DIR / "results"

    if args.mode in ("extract", "all"):
        rows = run_extract(args)
        if rows:
            write_csv(out_dir / "raw_extract.csv", EXTRACT_CSV_FIELDS, rows)
    if args.mode in ("reminder", "all"):
        rows = run_reminder(args)
        if rows:
            write_csv(out_dir / "raw_reminder.csv", REMINDER_CSV_FIELDS, rows)
    log("完成。下一步：python test/Test3/summarize.py")


if __name__ == "__main__":
    main()
