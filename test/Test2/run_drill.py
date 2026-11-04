# -*- coding: utf-8 -*-
"""run_drill.py — 实验二：降级链故障演练主脚本

对着真实降级链（AI/orchestrator.py + AI/model_router.py）注入三类故障，
每类各测 10 次，量化"断网也能答"到底多快答上、成功率多少、demo 兜底触发几次：

  baseline    无故障对照组（链路健康，正常滑链作答）
  fault_401   在线模型 API Key 全部改为非法值 → 模拟 401 鉴权失败
  fault_net   在线模型 endpoint 全部指向不可达端口 127.0.0.1:9 → 模拟断网/超时
  fault_demo  fault_401 基础上再停掉本地 Ollama → 最后一层也挂，验证 demo 兜底

每次运行记录：总耗时（= 链上失败模型失败耗时 + 接管模型作答耗时）、最终
provider、是否成功、是否触发 demo 兜底、是否被本地离线模型接管。
产出：test/Test2/results/drill_raw.csv（汇总用 python test/Test2/summarize.py）

用法：
  python test/Test2/run_drill.py                      # 全部 4 场景 × 10 次
  python test/Test2/run_drill.py --runs 10            # 显式指定次数
  python test/Test2/run_drill.py --scenarios fault_401,fault_net
  python test/Test2/run_drill.py --scenarios fault_demo --runs 1   # 冒烟
  python test/Test2/run_drill.py --dry-run            # 只打印计划不发请求
"""
import argparse
import csv
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

TEST2_DIR = Path(__file__).parent
ROOT = TEST2_DIR.parent.parent
sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

CSV_FIELDS = ["scenario", "run", "total_s", "ok", "provider", "demo_fallback",
              "offline_takeover", "answer_len", "error_note"]
UNREACHABLE_ENDPOINT = "http://127.0.0.1:9/v1/chat/completions"  # discard 端口，连接必然被拒
ONLINE_KEY_ENVS = ("GLM_API_KEY", "SILICONFLOW_API_KEY")
INVALID_KEY = "drill_invalid_key_exp2"   # 纯 ASCII：中文会让 httpx 报编码错而非 401
OLLAMA_BASE = "http://localhost:11434"
DEMO_PROVIDER = "demo"


def log(msg: str):
    print(msg, flush=True)


# ---------- 环境 ----------
def load_env():
    """加载项目根 .env（KEY=VALUE 逐行解析，不覆盖已有环境变量）"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text("utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def ollama_alive(timeout=1.5) -> bool:
    try:
        with urllib.request.urlopen(f"{OLLAMA_BASE}/", timeout=timeout):
            return True
    except Exception:
        return False


# ---------- Ollama 启停（场景 fault_demo 用） ----------
def stop_ollama() -> bool:
    """停掉本地 Ollama 服务；返回是否确认已停"""
    if not ollama_alive():
        return True
    if os.name != "nt":
        log("[fault_demo] 非 Windows 环境请手动停止 Ollama 后重跑")
        return False
    subprocess.run(["taskkill", "/IM", "ollama.exe", "/F"],
                   capture_output=True, text=True)
    for _ in range(10):   # 最多等 5 秒确认端口已关
        if not ollama_alive():
            return True
        time.sleep(0.5)
    log("[fault_demo] 警告：Ollama 疑似仍在运行，请手动关闭后重跑")
    return False


def start_ollama() -> bool:
    """拉起本地 Ollama 服务（演练结束后恢复现场）；返回是否确认已起"""
    if ollama_alive():
        return True
    if os.name == "nt":
        flags = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
        subprocess.Popen(["ollama", "serve"], creationflags=flags,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        subprocess.Popen(["ollama", "serve"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):   # 最多等 20 秒
        if ollama_alive():
            return True
        time.sleep(0.5)
    log("[恢复] 警告：Ollama 未能自动拉起，请手动执行 ollama serve")
    return False


# ---------- 故障注入（上下文管理式：进入注入 / 退出还原） ----------
class Fault401:
    """在线模型密钥全部替换为非法值 → 每个在线候选都吃 401"""
    def __enter__(self):
        self._saved = {k: os.environ.get(k) for k in ONLINE_KEY_ENVS}
        for k in ONLINE_KEY_ENVS:
            os.environ[k] = INVALID_KEY
        return self

    def __exit__(self, *exc):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class FaultNet:
    """在线模型 endpoint 全部改指不可达端口 → 连接拒绝/超时"""
    def __enter__(self):
        from AI import model_router
        self._saved = {}
        for mid, m in model_router._MODELS.items():
            if m.get("provider") == "ollama":
                continue   # 本地模型是最后一层，不注入
            self._saved[mid] = m["endpoint"]
            m["endpoint"] = UNREACHABLE_ENDPOINT
        return self

    def __exit__(self, *exc):
        from AI import model_router
        for mid, ep in self._saved.items():
            model_router._MODELS[mid]["endpoint"] = ep


SCENARIOS = ("baseline", "fault_401", "fault_net", "fault_demo")
SCENARIO_DESC = {
    "baseline":   "无故障对照组",
    "fault_401":  "在线密钥全部非法（401）",
    "fault_net":  "在线 endpoint 不可达（断网/超时）",
    "fault_demo": "在线 401 + 本地 Ollama 停机（demo 兜底）",
}


# ---------- 单次演练 ----------
def drill_once(utterance: str) -> dict:
    """跑一次完整 orchestrator.run，记录总耗时与最终接管者"""
    from AI import orchestrator
    t0 = time.perf_counter()
    err = ""
    try:
        out = orchestrator.run(user_id=90210, utterance=utterance, ctx=None)
        provider = out.get("provider", "")
        answer = out.get("answer", "")
    except Exception as e:   # noqa: BLE001
        provider, answer = "", ""
        err = f"{type(e).__name__}: {e}"[:120]
    total_s = round(time.perf_counter() - t0, 3)
    ok = bool(answer.strip())
    return {"total_s": total_s, "ok": ok, "provider": provider,
            "demo_fallback": provider == DEMO_PROVIDER,
            "offline_takeover": provider.startswith("ollama:"),
            "answer_len": len(answer or ""), "error_note": err}


def append_row(out_csv: Path, row: dict):
    new_file = not out_csv.exists()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)


def precheck(scenario: str) -> bool:
    """场景前置检查：baseline 需要在线 Key + Ollama；fault_demo 需要 Ollama 在跑"""
    missing = [k for k in ONLINE_KEY_ENVS if not os.environ.get(k)]
    if scenario in ("baseline",) and missing:
        log(f"[跳过] {scenario}：.env 缺 {missing}，对照组测出来没有意义")
        return False
    if scenario == "fault_demo" and not ollama_alive():
        log("[fault_demo] Ollama 当前未运行：fault_demo 需要先有 Ollama 才能演练'把它停掉'")
        log("            请先启动 Ollama（ollama serve）后重跑该场景")
        return False
    return True


def run_scenario(scenario: str, runs: int, out_csv: Path, utterance: str):
    log(f"\n=== 场景 {scenario}：{SCENARIO_DESC[scenario]} × {runs} 次 ===")
    stop_ollama_after = False
    if scenario == "fault_demo":
        log("[fault_demo] 注入动作：taskkill 停掉本地 Ollama（演练结束自动恢复）")
        if not stop_ollama():
            log("[fault_demo] Ollama 停不掉，本场景中止")
            return
        stop_ollama_after = True
    try:
        if scenario == "fault_401":
            with Fault401():
                _loop(scenario, runs, out_csv, utterance)
        elif scenario == "fault_net":
            with FaultNet():
                _loop(scenario, runs, out_csv, utterance)
        elif scenario == "fault_demo":
            with Fault401():
                _loop(scenario, runs, out_csv, utterance)
        else:
            _loop(scenario, runs, out_csv, utterance)
    finally:
        if stop_ollama_after:
            log("[恢复] 重新拉起本地 Ollama …")
            start_ollama()


def _loop(scenario: str, runs: int, out_csv: Path, utterance: str):
    for i in range(1, runs + 1):
        r = drill_once(utterance)
        append_row(out_csv, {"scenario": scenario, "run": i, **r})
        tag = ("demo兜底" if r["demo_fallback"] else
               "离线接管" if r["offline_takeover"] else
               "在线命中" if r["ok"] else "失败")
        log(f"  [{scenario}] #{i:>2}/{runs} ok={r['ok']} {tag:<4} "
            f"provider={r['provider'] or 'N/A':<22} 耗时 {r['total_s']:>7.2f}s "
            f"{('err=' + r['error_note']) if r['error_note'] else ''}")


def main():
    ap = argparse.ArgumentParser(description="实验二：降级链故障演练（3 类注入 × N 次）")
    ap.add_argument("--scenarios", default="all",
                    help="逗号分隔：baseline,fault_401,fault_net,fault_demo 或 all")
    ap.add_argument("--runs", type=int, default=10, help="每场景运行次数，默认 10")
    ap.add_argument("--out", default="", help="输出 CSV，默认 test/Test2/results/drill_raw.csv")
    ap.add_argument("--utterance", default="你好，请用一句话介绍你自己。",
                    help="每次演练使用的用户话术（不含工具触发词）")
    ap.add_argument("--dry-run", action="store_true", help="只打印执行计划，不发请求")
    args = ap.parse_args()

    load_env()
    out_csv = Path(args.out) if args.out else TEST2_DIR / "results" / "drill_raw.csv"
    scenarios = SCENARIOS if args.scenarios == "all" else \
        [s.strip() for s in args.scenarios.split(",") if s.strip()]
    bad = [s for s in scenarios if s not in SCENARIOS]
    if bad:
        log(f"[错误] 未知场景 {bad}，可选：{SCENARIOS}")
        sys.exit(1)

    log(f"演练计划：{len(scenarios)} 场景 × {args.runs} 次 → {out_csv}")
    for s in scenarios:
        log(f"  {s:<12} {SCENARIO_DESC[s]}")
    if args.dry_run:
        log(f"[dry-run] 共 {len(scenarios) * args.runs} 次请求，未发送。")
        return

    if not ollama_alive():
        log("[提示] 本地 Ollama 未运行：baseline/fault_401/fault_net 的'离线接管'"
            "将不可用，会直接落 demo 兜底。建议先 ollama serve。")

    for s in scenarios:
        if precheck(s):
            run_scenario(s, args.runs, out_csv, args.utterance)
    log(f"\n完成。原始数据：{out_csv}")
    log(f"下一步：python test/Test2/summarize.py   # 出'故障场景 × 恢复耗时'表")


if __name__ == "__main__":
    main()
