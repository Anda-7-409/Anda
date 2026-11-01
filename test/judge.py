# -*- coding: utf-8 -*-
"""judge.py — 实验一判分器（规则先于实验冻结，对应实验文档 5.2 节）
四类能力判分：
  tool_use  : 工具选择正确率 Acc_tool（工具名 + 禁用项 + task 关键参数）
  chat      : 关键点命中率 Hit_kp（每个关键点给同义变体表，命中全部才算对）
  code      : 单元测试通过率 Pass_ut（抽取代码块，子进程执行预置断言，10s 超时）
  reasoning : 答案正确率 Acc_ans（数字解析比对 / 关键词匹配）
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

SANDBOX_TIMEOUT = 10  # 秒，对应实验文档 5.2 Pass_ut 规则


def _norm(text: str) -> str:
    return (text or "").strip().lower()


def judge_tool_use(case: dict, state: dict):
    """state: {"content": str, "tool_calls": [{"name","arguments"}]}"""
    expect = case.get("expect", {})
    calls = state.get("tool_calls") or []
    names = [c.get("name", "") for c in calls]
    args_text = " ".join(str(c.get("arguments") or "") for c in calls)
    if not names:
        return 0.0, False, "模型未发起任何工具调用（纯文本回答）"
    any_of = expect.get("any_of") or [expect.get("tool")]
    hit = any(t in names for t in any_of if t)
    forbid = [t for t in expect.get("forbid", []) if t in names]
    if forbid:
        return 0.0, False, f"调用了禁用工具 {forbid}（实际调用 {names}）"
    missing = [k for k in expect.get("params_must", []) if k not in args_text]
    if not hit:
        return 0.0, False, f"期望 {any_of}，实际调用 {names}"
    if missing:
        return 0.0, False, f"工具选对但 task 缺关键参数 {missing}（arguments={args_text[:120]}）"
    return 1.0, True, f"正确调用 {names}"


def judge_chat(case: dict, state: dict):
    kps = case.get("kp", [])
    if not kps:
        return 0.0, False, "用例缺少 kp 字段"
    text = _norm(state.get("content"))
    hits, missed = 0, []
    for i, variants in enumerate(kps):
        if any(_norm(v) in text for v in variants):
            hits += 1
        else:
            missed.append(f"kp{i}:{variants}")
    score = hits / len(kps)
    return score, score >= 1.0, f"命中 {hits}/{len(kps)}" + (f"，未命中 {missed}" if missed else "")


_NUM_RE = re.compile(r"-?\d+(?:\.\d+)?")


def judge_reasoning(case: dict, state: dict):
    ans = case.get("answer")
    if ans is None:
        return 0.0, False, "用例缺少 answer 字段"
    text = state.get("content") or ""
    if isinstance(ans, (int, float)):
        found = [float(x) for x in _NUM_RE.findall(text.replace(",", "").replace("，", ""))]
        if any(abs(x - float(ans)) < 1e-6 for x in found):
            return 1.0, True, f"命中答案 {ans}"
        return 0.0, False, f"期望 {ans}，解析到数字 {found[:8]}"
    if _norm(str(ans)) in _norm(text):
        return 1.0, True, f"命中答案 {ans}"
    return 0.0, False, f"期望关键词 {ans} 未出现"


_CODE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def _extract_code(text: str) -> str:
    blocks = _CODE_RE.findall(text or "")
    if blocks:
        return max(blocks, key=len).strip()
    return text.strip() if ("def " in text or "class " in text) else ""


def judge_code(case: dict, state: dict):
    tests = case.get("tests", [])
    if not tests:
        return 0.0, False, "用例缺少 tests 字段"
    code = _extract_code(state.get("content"))
    if not code:
        return 0.0, False, "未找到代码块（无 ```python 围栏且无 def/class）"
    harness = code + "\n" + "\n".join(tests) + "\nprint('__EVAL_PASS__')\n"
    with tempfile.NamedTemporaryFile("w", suffix=".py", encoding="utf-8", delete=False) as f:
        f.write(harness)
        tmp = f.name
    try:
        proc = subprocess.run([sys.executable, tmp], capture_output=True,
                              text=True, timeout=SANDBOX_TIMEOUT,
                              cwd=tempfile.gettempdir())
        if proc.returncode == 0 and "__EVAL_PASS__" in proc.stdout:
            return 1.0, True, "单元测试全部通过"
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        return 0.0, False, f"断言失败/异常：{tail[-1][:150] if tail else '无输出'}"
    except subprocess.TimeoutExpired:
        return 0.0, False, f"沙箱执行超时（>{SANDBOX_TIMEOUT}s）"
    finally:
        try:
            Path(tmp).unlink()
        except OSError:
            pass


def judge_case(ability: str, case: dict, state: dict):
    """返回 (score 0~1, judge_result bool, detail str)"""
    try:
        if ability == "tool_use":
            return judge_tool_use(case, state)
        if ability == "chat":
            return judge_chat(case, state)
        if ability == "reasoning":
            return judge_reasoning(case, state)
        if ability == "code":
            return judge_code(case, state)
        raise ValueError(f"未知能力 {ability}")
    except Exception as e:  # 判分器自身异常不得中断评测，记失败并留痕
        return 0.0, False, f"判分器异常：{e}"
