# -*- coding: utf-8 -*-
"""summarize.py — 实验三结果汇总：raw_extract.csv / raw_reminder.csv → summary.md

产出四张表（答辩/论文直接可贴）：
  表A 课表抽取 × 难度标签（验证"架构选型在烂图上也站得住"）
  表B 课表抽取总体指标（宏平均/微平均/图片级全对率）
  表C 提醒指令 × 类型（clock/relative/delta/absolute/weekday/fuzzy）
  表D 错误案例榜（自动挑最差 3~5 个案例，供人工归因写"典型错误案例分析"）

用法：python test/Test3/summarize.py
"""
import csv
import sys
from collections import defaultdict
from pathlib import Path

TEST3_DIR = Path(__file__).parent
RESULTS = TEST3_DIR / "results"
SUMMARY = RESULTS / "summary.md"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def log(msg):
    print(msg, flush=True)


def read_csv(name):
    p = RESULTS / name
    if not p.is_file():
        return []
    with p.open(encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def fnum(v, nd=2):
    try:
        return f"{float(v):.{nd}f}"
    except (TypeError, ValueError):
        return "-"


def pct(v, nd=1):
    try:
        return f"{float(v) * 100:.{nd}f}%"
    except (TypeError, ValueError):
        return "-"


def md_table(header, rows):
    lines = ["| " + " | ".join(header) + " |",
             "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(lines)


# ---------- 表A/B：课表抽取 ----------
def extract_tables(rows):
    by_tag = defaultdict(list)
    for r in rows:
        by_tag[r["tag"] or r["image_id"]].append(r)
    ta = []
    for tag, rs in sorted(by_tag.items()):
        n = len(rs)
        ta.append([
            tag, n,
            fnum(sum(int(x["gt_total"]) for x in rs) / n, 1),
            pct(sum(float(x["course_acc"]) for x in rs) / n),
            pct(sum(int(x["image_exact"]) for x in rs) / n),
            fnum(sum(int(x["extra"]) for x in rs) / n, 1),
            fnum(sum(float(x["latency_s"]) for x in rs) / n, 1),
        ])
    table_a = md_table(
        ["难度标签", "轮次", "平均真值课程数", "课程级准确率", "图片全对率", "平均多检/图", "平均时延(s)"], ta)

    n = len(rows)
    gt_sum = sum(int(x["gt_total"]) for x in rows)
    matched_sum = sum(int(x["matched"]) for x in rows)
    den_room = [x for x in rows if str(x["room_acc"]).strip()]
    den_tea = [x for x in rows if str(x["teacher_acc"]).strip()]
    micro = matched_sum / gt_sum if gt_sum else 0
    macro = sum(float(x["course_acc"]) for x in rows) / n if n else 0
    exact = sum(int(x["image_exact"]) for x in rows) / n if n else 0
    err_dist = defaultdict(int)
    for x in rows:
        if x["error_type"] and x["error_type"] != "none":
            err_dist[x["error_type"]] += 1
    tb_rows = [
        ["微平均 course_acc（matched/gt 总和）", pct(micro)],
        ["宏平均 course_acc（每轮准确率均值）", pct(macro)],
        ["图片级全对率（matched==gt 且 extra==0）", pct(exact)],
        ["教室辅助准确率", pct(sum(float(x["room_acc"]) for x in den_room) / len(den_room)) if den_room else "-"],
        ["教师辅助准确率", pct(sum(float(x["teacher_acc"]) for x in den_tea) / len(den_tea)) if den_tea else "-"],
        ["平均时延", f"{fnum(sum(float(x['latency_s']) for x in rows) / n, 1)} s" if n else "-"],
        ["失败轮次", f"{sum(1 for x in rows if x['ok'] == '0')} / {n}"
         + ("（" + ", ".join(f"{k}×{v}" for k, v in err_dist.items()) + "）" if err_dist else "")],
    ]
    table_b = md_table(["指标", "数值"], tb_rows)
    return table_a, table_b


# ---------- 表C/D：提醒指令 ----------
def reminder_tables(rows):
    by_kind = defaultdict(list)
    for r in rows:
        by_kind[r["kind"]].append(r)
    order = ["clock", "relative", "delta", "absolute", "weekday", "fuzzy"]
    tc = []
    for kind in order:
        rs = by_kind.get(kind)
        if not rs:
            continue
        n = len(rs)
        passed = sum(int(x["pass"]) for x in rs)
        err_dist = defaultdict(int)
        for x in rs:
            if x["error_type"] and x["error_type"] != "none":
                err_dist[x["error_type"]] += 1
        tc.append([
            kind, n, pct(passed / n),
            f"{sum(int(x['type_ok']) for x in rs)}/{n}" if kind != "fuzzy" else "-",
            f"{sum(int(x['time_ok']) for x in rs)}/{n}" if kind != "fuzzy" else "-",
            fnum(sum(float(x["latency_s"]) for x in rs) / n, 1),
            ", ".join(f"{k}×{v}" for k, v in err_dist.items()) or "-",
        ])
    total_n = len(rows)
    total_pass = sum(int(x["pass"]) for x in rows)
    tc.append(["**合计**", total_n, f"**{pct(total_pass / total_n)}**" if total_n else "-",
               "-", "-", fnum(sum(float(x["latency_s"]) for x in rows) / total_n, 1) if total_n else "-", "-"])
    table_c = md_table(["类型", "条数×轮次", "通过率", "内容对", "时间对", "平均时延(s)", "错误分布"], tc)

    # 表D：错误案例榜——课程抽取最差 3 个 + 提醒失败全部（上限 5）
    worst = sorted((r for r in read_csv("raw_extract.csv")
                    if r["ok"] == "1" and int(r["gt_total"]) > 0),
                   key=lambda r: float(r["course_acc"]))[:3]
    rem_fail = [r for r in rows if r["pass"] == "0"]
    td = []
    for r in worst:
        td.append(["课表抽取", r["image_id"],
                   f"tag={r['tag']} course_acc={pct(float(r['course_acc']))} "
                   f"matched={r['matched']}/{r['gt_total']} 多检={r['extra']}",
                   r["missed_detail"] or "-", r["raw_preview"][:120]])
    for r in rem_fail[:2]:
        td.append(["提醒指令", r["case_id"],
                   f"kind={r['kind']} type_ok={r['type_ok']} time_ok={r['time_ok']} err={r['error_type']}",
                   f"期望 {r['expected_time'] or '(期望追问)'} / 实得 {r['got_time'] or '-'}",
                   r["raw_preview"][:120]])
    table_d = md_table(["模块", "案例", "指标", "缺失明细/时间对比", "模型原始输出节选"], td) \
        if td else "（无失败案例，全部通过——错误案例分析章节可写'边界用例全部正确，体现鲁棒性'）"
    return table_c, table_d, len(rem_fail), len(worst)


def main():
    ext_rows = read_csv("raw_extract.csv")
    rem_rows = read_csv("raw_reminder.csv")
    if not ext_rows and not rem_rows:
        log("results/ 下没有 raw_extract.csv / raw_reminder.csv，请先跑 run_eval.py")
        sys.exit(1)

    parts = ["# 实验三：抽取准确率评测汇总", ""]
    if ext_rows:
        ta, tb = extract_tables(ext_rows)
        parts += ["## 表A 课表抽取 × 难度标签", "", ta, "",
                  "## 表B 课表抽取总体指标", "", tb, ""]
    if rem_rows:
        tc, td, n_fail, n_worst = reminder_tables(rem_rows)
        parts += ["## 表C 提醒指令 × 类型", "", tc, "",
                  "## 表D 错误案例榜（供'典型错误案例分析'归因）", "", td, "",
                  f"> 错误案例素材：课表最差 {n_worst} 例 + 提醒失败 {n_fail} 例。"
                  "归因套路：现象（模型输出了什么）→ 根因（透视/摩尔纹/连堂拆分/模糊表达编造…）→ 对策（提示词约束/前置纠偏…）。", ""]
    SUMMARY.write_text("\n".join(parts), encoding="utf-8")
    log(f"已写入：{SUMMARY}")
    log("人工归因提示：表D 只给出'最差案例'候选，答辩用的根因分析需要对着 raw_preview 列逐条看。")


if __name__ == "__main__":
    main()
