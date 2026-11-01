# -*- coding: utf-8 -*-
"""validate_cases.py — 评测用例集格式校验（实验文档 6.3 节 S1 验收标准）
检查：JSON 可解析、字段齐全、id 唯一、工具名在注册表内、chat 有 kp、
code 有可执行 tests、reasoning 有 answer、tool_use 的 expect 合法。
"""
import json
import re
import sys
from pathlib import Path

TEST_DIR = Path(__file__).parent
ROOT = TEST_DIR.parent
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_CODE_RE = re.compile(r"```(?:python|py)?\s*\n(.*?)```", re.S)


def parse_tool_names() -> set:
    src = (ROOT / "Backend" / "service" / "agent_service.py").read_text("utf-8")
    return set(re.findall(r'orchestrator\.TOOLS\["(\w+)"\]', src))


def validate(ability: str, cases: list, tools: set) -> list:
    errors = []
    ids = set()
    for i, c in enumerate(cases):
        tag = f"{ability}[{i}]"
        cid = c.get("id", "")
        if not cid or cid in ids:
            errors.append(f"{tag}: id 缺失或重复（{cid}）")
        ids.add(cid)
        if not c.get("utterance"):
            errors.append(f"{cid}: 缺 utterance")
        if ability == "chat" and not c.get("kp"):
            errors.append(f"{cid}: chat 用例缺 kp（关键点列表）")
        if ability == "reasoning" and c.get("answer") is None:
            errors.append(f"{cid}: reasoning 用例缺 answer")
        if ability == "code":
            tests = c.get("tests", [])
            if not tests or not all(isinstance(t, str) and t.strip() for t in tests):
                errors.append(f"{cid}: code 用例 tests 为空或格式不对")
            else:
                calls = set()
                for t in tests:
                    calls.update(re.findall(r"\b([a-zA-Z_]\w*)\s*\(", t))
                calls -= {"assert", "print", "abs", "round", "str", "int", "float", "len", "range", "set", "list", "dict"}
                utt = c.get("utterance", "")
                if not any(fn in utt for fn in calls):
                    errors.append(f"{cid}: tests 调用的函数 {sorted(calls)} 未出现在题目描述中")
        if ability == "tool_use":
            expect = c.get("expect", {})
            names = set(expect.get("any_of") or ([expect.get("tool")] if expect.get("tool") else []))
            bad = {t for t in names if t and t not in tools}
            if bad:
                errors.append(f"{cid}: 期望工具 {bad} 不在注册表 {sorted(tools)}")
            for t in expect.get("forbid", []):
                if t not in tools:
                    errors.append(f"{cid}: forbid 工具 {t} 不在注册表")
    return errors


def main():
    tools = parse_tool_names()
    print(f"工具注册表解析：{len(tools)} 个 -> {sorted(tools)}")
    total, all_errors = 0, []
    for ab in ("chat", "tool_use", "code", "reasoning"):
        f = TEST_DIR / "cases" / f"{ab}.json"
        try:
            cases = json.loads(f.read_text("utf-8"))
        except Exception as e:
            all_errors.append(f"{ab}.json 解析失败：{e}")
            continue
        errs = validate(ab, cases, tools)
        total += len(cases)
        status = "PASS" if not errs else f"FAIL（{len(errs)} 处）"
        print(f"  {ab}.json: {len(cases)} 条 {status}")
        all_errors += errs
    if all_errors:
        print("\n问题清单：")
        for e in all_errors:
            print(f"  - {e}")
        sys.exit(1)
    print(f"\n全部通过，共 {total} 条用例。")


if __name__ == "__main__":
    main()
