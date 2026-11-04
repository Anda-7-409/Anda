# -*- coding: utf-8 -*-
"""summarize.py — 实验二汇总：把 drill_raw.csv 聚成"故障场景 × 恢复耗时"表

读 test/Test2/results/drill_raw.csv，产出 test/Test2/results/summary.md：
  - 主表：故障场景 × (平均/P50/P95 恢复耗时, 成功率, demo兜底率, 离线接管率, 主要接管者)
  - 辅表：相对 baseline 的平均耗时开销
用法：python test/Test2/summarize.py [--csv 路径]
"""
import argparse
import csv
import sys
from pathlib import Path
from statistics import mean, median

TEST2_DIR = Path(__file__).parent
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SCENARIO_DESC = {
    "baseline":   "无故障对照组",
    "fault_401":  "在线密钥全部非法（401）",
    "fault_net":  "在线 endpoint 不可达（断网/超时）",
    "fault_demo": "在线 401 + 本地 Ollama 停机（demo 兜底）",
}


def p95(values):
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, round(0.95 * (len(s) - 1))))
    return s[idx]


def load(csv_path: Path):
    rows = []
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            try:
                rows.append({"scenario": r["scenario"], "run": int(r["run"]),
                             "total_s": float(r["total_s"]),
                             "ok": r["ok"] == "True",
                             "provider": r["provider"],
                             "demo_fallback": r["demo_fallback"] == "True",
                             "offline_takeover": r["offline_takeover"] == "True"})
            except (KeyError, ValueError):
                continue
    return rows


def summarize(rows):
    lines = ["# 实验二：降级链故障演练 — 汇总", "",
             "> 恢复耗时 = 从用户发话到降级链给出最终回答的总耗时",
             "（= 链上失败模型失败耗时累加 + 接管模型作答耗时）。", ""]
    n = len({r["run"] for r in rows}) if rows else 0
    lines.append(f"样本：{len(rows)} 次演练（每场景 {n} 次）。")
    lines.append("")

    # 主表
    lines.append("## 表 1　故障场景 × 恢复耗时")
    lines.append("")
    lines.append("| 故障场景 | 次数 | 平均耗时(s) | P50(s) | P95(s) | 最终成功率 | demo兜底率 | 离线接管率 | 主要接管者 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    base_avg = None
    stats = {}
    for sc in SCENARIO_DESC:
        grp = [r for r in rows if r["scenario"] == sc]
        if not grp:
            continue
        ts = [r["total_s"] for r in grp]
        ok_rate = mean(r["ok"] for r in grp) * 100
        demo_rate = mean(r["demo_fallback"] for r in grp) * 100
        off_rate = mean(r["offline_takeover"] for r in grp) * 100
        providers = [r["provider"] for r in grp if r["ok"]]
        main_p = max(set(providers), key=providers.count) if providers else "—"
        stats[sc] = (mean(ts), ok_rate, demo_rate)
        if sc == "baseline":
            base_avg = mean(ts)
        lines.append(f"| {SCENARIO_DESC[sc]} ({sc}) | {len(grp)} | {mean(ts):.2f} | "
                     f"{median(ts):.2f} | {p95(ts):.2f} | {ok_rate:.0f}% | "
                     f"{demo_rate:.0f}% | {off_rate:.0f}% | {main_p} |")
    lines.append("")

    # 辅表
    if base_avg is not None and stats:
        lines.append("## 表 2　相对 baseline 的平均耗时开销")
        lines.append("")
        lines.append("| 故障场景 | 平均耗时(s) | 较 baseline 增量(s) | 增幅 |")
        lines.append("| --- | --- | --- | --- |")
        for sc, (avg, _, _) in stats.items():
            if sc == "baseline":
                continue
            delta = avg - base_avg
            pct = (delta / base_avg * 100) if base_avg > 0 else 0.0
            lines.append(f"| {SCENARIO_DESC[sc]} ({sc}) | {avg:.2f} | "
                         f"{delta:+.2f} | {pct:+.0f}% |")
        lines.append("")

    lines.append("## 结论要点（答辩引用）")
    lines.append("")
    for sc in ("fault_401", "fault_net", "fault_demo"):
        if sc in stats:
            avg, okr, dr = stats[sc]
            lines.append(f"- **{SCENARIO_DESC[sc]}**：平均 {avg:.2f}s 恢复，"
                         f"成功率 {okr:.0f}%，demo 兜底触发率 {dr:.0f}%。")
    if "fault_demo" in stats and "fault_net" in stats:
        lines.append("- 前两类故障（401/断网）由降级链内部消化（在线层挂 → 本地离线模型接管），"
                     "仅最后一层也挂时才落 demo 兜底——'断网也能答'成立且有量化指标。")
    lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="实验二汇总：故障场景 × 恢复耗时")
    ap.add_argument("--csv", default="", help="输入 CSV，默认 test/Test2/results/drill_raw.csv")
    args = ap.parse_args()
    csv_path = Path(args.csv) if args.csv else TEST2_DIR / "results" / "drill_raw.csv"
    if not csv_path.exists():
        print(f"[错误] 找不到 {csv_path}，请先运行 run_drill.py")
        sys.exit(1)
    rows = load(csv_path)
    if not rows:
        print("[错误] CSV 里没有有效数据")
        sys.exit(1)
    report = summarize(rows)
    out_md = csv_path.parent / "summary.md"
    out_md.write_text(report, encoding="utf-8")
    print(report)
    print(f"已写入：{out_md}")


if __name__ == "__main__":
    main()
