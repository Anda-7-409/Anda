# -*- coding: utf-8 -*-
"""summarize.py — 实验一数据汇总：从 raw.csv 产出实验文档第 7 节的表 A/B/C
  表 A  模型×能力 质量表（准确率 %，仅统计调用成功轮次）
  表 B  模型×能力 性能表（TTFT P50/P95、耗时 P95、成功率）
  表 C  现行权重序 vs 实验质量序 对照（H1 检验：秩差）
输出：test/results/summary.md，同时打印到控制台。
"""
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

TEST_DIR = Path(__file__).parent
ROOT = TEST_DIR.parent
ABILITIES = ("chat", "tool_use", "code", "reasoning")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def quantile(sorted_vals: list, q: float) -> float:
    """线性插值分位数（等价 numpy.quantile 默认法）"""
    if not sorted_vals:
        return float("nan")
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    idx = q * (len(sorted_vals) - 1)
    lo, hi = int(idx), min(int(idx) + 1, len(sorted_vals) - 1)
    frac = idx - lo
    return sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac


def load_rows(csv_path: Path) -> list:
    with csv_path.open("r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def group_stats(rows: list) -> dict:
    """(model_id, ability) -> {acc, sr, ttft_p50, ttft_p95, lat_p95, n}"""
    g = defaultdict(lambda: {"ok_judge": [], "ok": [], "ttft": [], "lat": []})
    for r in rows:
        key = (r["model_id"], r["ability"])
        if r["ok"] == "True":
            g[key]["ok_judge"].append(float(r["score"]))
            g[key]["ok"].append(1)
            if r["ttft_s"] not in ("", None, "None"):
                g[key]["ttft"].append(float(r["ttft_s"]))
            if r["latency_s"] not in ("", None, "None"):
                g[key]["lat"].append(float(r["latency_s"]))
        else:
            g[key]["ok"].append(0)
    out = {}
    for key, v in g.items():
        n = len(v["ok"])
        out[key] = {
            "n": n,
            "acc": (sum(v["ok_judge"]) / len(v["ok_judge"]) * 100) if v["ok_judge"] else float("nan"),
            "sr": sum(v["ok"]) / n * 100 if n else 0.0,
            "ttft_p50": quantile(sorted(v["ttft"]), 0.5) if v["ttft"] else float("nan"),
            "ttft_p95": quantile(sorted(v["ttft"]), 0.95) if v["ttft"] else float("nan"),
            "lat_p95": quantile(sorted(v["lat"]), 0.95) if v["lat"] else float("nan"),
        }
    return out


def rank_map(stats: dict, ability: str, value_key: str, reverse=True) -> list:
    """某能力下按指标排序的 model_id 列表（降序），跳过无数据/无权重的模型"""
    items = [(mid, s[value_key]) for (mid, ab), s in stats.items()
             if ab == ability and s["n"] > 0 and s[value_key] == s[value_key]]  # 过滤 NaN
    items.sort(key=lambda x: x[1], reverse=reverse)
    return [mid for mid, _ in items]


def main():
    import argparse
    ap = argparse.ArgumentParser(description="实验一数据汇总")
    ap.add_argument("--csv", default=str(TEST_DIR / "results" / "raw.csv"),
                    help="原始数据 CSV 路径，默认 test/results/raw.csv")
    args = ap.parse_args()
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"找不到 {csv_path}，请先运行 run_eval.py")
        sys.exit(1)
    rows = load_rows(csv_path)
    stats = group_stats(rows)
    registry = {m["model_id"]: m for m in
                json.loads((ROOT / "AI" / "models.json").read_text("utf-8"))["models"]}

    lines = ["# 实验一汇总（自动生成，来源 results/raw.csv）", ""]

    # 表 A
    lines += ["## 表 A：模型×能力 质量表（准确率 %，仅计调用成功轮次）", ""]
    all_models = sorted({mid for mid, _ in stats})
    header = "| model_id | " + " | ".join(ABILITIES) + " |"
    lines += [header, "|" + "---|" * (len(ABILITIES) + 1)]
    for mid in all_models:
        cells = [f"`{mid}`"]
        for ab in ABILITIES:
            s = stats.get((mid, ab))
            cells.append(f"{s['acc']:.1f}" if s and s["n"] else "—")
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    # 表 B
    lines += ["## 表 B：模型×能力 性能表（s / %）", ""]
    lines += ["| model_id | 能力 | TTFT P50 | TTFT P95 | 耗时 P95 | 成功率 | 样本数 |",
              "|---|---|---|---|---|---|---|"]
    for mid in all_models:
        for ab in ABILITIES:
            s = stats.get((mid, ab))
            if not s or not s["n"]:
                continue
            tt50 = f"{s['ttft_p50']:.2f}" if s["ttft_p50"] == s["ttft_p50"] else "—"
            tt95 = f"{s['ttft_p95']:.2f}" if s["ttft_p95"] == s["ttft_p95"] else "—"
            lat = f"{s['lat_p95']:.2f}" if s["lat_p95"] == s["lat_p95"] else "—"
            lines.append(f"| `{mid}` | {ab} | {tt50} | {tt95} | {lat} | "
                         f"{s['sr']:.1f}% | {s['n']} |")
    lines.append("")

    # 表 C：权重序 vs 质量序（H1 检验）
    lines += ["## 表 C：现行权重序 vs 实验质量序（H1 检验）", ""]
    lines += ["| 能力 | 现行权重序 | 实验质量序 | 秩差 | 结论 |",
              "|---|---|---|---|---|"]
    for ab in ABILITIES:
        w_rank = rank_map({}, ab, "_")  # 占位，下面单独算
        weight_sorted = sorted(
            [mid for mid in registry if registry[mid]["ability_weights"].get(ab, 0) > 0],
            key=lambda mid: -registry[mid]["ability_weights"][ab])
        acc_sorted = rank_map(stats, ab, "acc")
        if not acc_sorted:
            lines.append(f"| {ab} | {' > '.join(weight_sorted) or '—'} | 无数据 | — | 待评测 |")
            continue
        diffs = []
        for i, mid in enumerate(weight_sorted):
            if mid in acc_sorted:
                diffs.append(abs(i - acc_sorted.index(mid)))
        avg_diff = sum(diffs) / len(diffs) if diffs else float("nan")
        concl = "基本一致" if (avg_diff == avg_diff and avg_diff <= 1.0) else "需调整"
        lines.append(f"| {ab} | {' > '.join(weight_sorted)} | {' > '.join(acc_sorted)} "
                     f"| {avg_diff:.2f} | {concl} |")
    lines.append("")
    lines += ["> 秩差 = 同一模型在权重序与质量序中位次的平均差；≤1 视为 H1 成立（排序基本一致）。", ""]

    report = "\n".join(lines)
    stem = "summary" if csv_path.stem == "raw" else f"summary_{csv_path.stem}"
    out = csv_path.parent / f"{stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report, encoding="utf-8")
    print(report)
    print(f"已写入 {out}")


if __name__ == "__main__":
    main()
