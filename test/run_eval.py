# -*- coding: utf-8 -*-
"""run_eval.py — 实验一主评测脚本：绕过滑链，直连单模型测量质量与性能
对应实验文档 6.1~6.3 节。请求与线上同形：
  - 系统提示词取 AI/prompt.json 的 orchestrator.sys_fc
  - tool_use 能力携带与 orchestrator._fc_tools() 相同的通用 {task} schema，
    工具描述直接解析 Backend/service/agent_service.py 的注册文本
  - 流式请求采集 TTFT（首块延迟），SSE 解析逻辑与 AI/model_router.py 一致
用法：python run_eval.py --ability tool_use --model glm-4.7-flash --rounds 3
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

TEST_DIR = Path(__file__).parent
ROOT = TEST_DIR.parent
sys.path.insert(0, str(TEST_DIR))
from judge import judge_case  # noqa: E402

CSV_FIELDS = ["case_id", "ability", "model_id", "round", "provider", "ok",
              "score", "judge_result", "error_type", "ttft_s", "latency_s",
              "resp_preview"]
ABILITIES = ("chat", "tool_use", "code", "reasoning")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------- 配置加载 ----------
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


def load_registry() -> dict:
    data = json.loads((ROOT / "AI" / "models.json").read_text("utf-8"))
    return {m["model_id"]: m for m in data["models"]}


def load_sys_fc() -> str:
    """与 orchestrator 线上一致的系统提示词"""
    try:
        data = json.loads((ROOT / "AI" / "prompt.json").read_text("utf-8"))
        return data["orchestrator"]["sys_fc"]
    except Exception as e:
        print(f"[警告] 读取 sys_fc 失败（{e}），使用空系统提示词")
        return ""


_DESC_RE = re.compile(
    r'orchestrator\.TOOLS\["(\w+)"\]\s*=\s*\{\s*"desc":\s*"((?:[^"\\]|\\.)*)"')


def parse_tool_registry() -> dict:
    """从 agent_service.py 源码解析 14 个工具的注册描述（与线上 FC desc 同文）"""
    src = (ROOT / "Backend" / "service" / "agent_service.py").read_text("utf-8")
    tools = {}
    for name, desc in _DESC_RE.findall(src):
        tools[name] = desc.replace('\\"', '"')
    return tools


def build_fc_tools(tools: dict) -> list:
    """与 orchestrator._fc_tools() 同形：全部工具共用 {task} 通用参数"""
    return [{"type": "function", "function": {
        "name": name, "description": desc,
        "parameters": {"type": "object", "properties": {
            "task": {"type": "string", "description":
                     "要执行的任务描述，需包含所有必要细节（课程名/时间/地点/查询内容等）"}},
        "required": ["task"]}}}
        for name, desc in tools.items()]


# ---------- 单模型请求（流式采集 TTFT，SSE 解析与 model_router 一致） ----------
def _sse_obj(line: str):
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if data == "[DONE]":
        return None
    try:
        return json.loads(data)
    except Exception:
        return None


def call_model_once(model: dict, messages: list, tools, sys_fc: str) -> dict:
    """发起一次流式请求。返回 {ok, content, tool_calls, ttft_s, latency_s, error_type}
    流式失败且未收到任何事件时回退非流式（与线上 chat_stream 的兜底思路一致）。"""
    endpoint = model["endpoint"]
    headers = {"Authorization": f"Bearer {os.environ[model['api_key_env']]}"
               } if model.get("api_key_env") else {}
    payload = {"messages": messages, "stream": True, "model": model["model_name"],
               **model.get("extra_body", {})}
    if tools:
        payload["tools"] = tools
    timeout = model.get("stream_timeout", model.get("timeout", 60))
    t0 = time.monotonic()
    ttft, content, pending, stream_broke = None, "", {}, False
    try:
        with httpx.stream("POST", endpoint, headers=headers, json=payload,
                          timeout=timeout) as r:
            if r.status_code >= 400:
                body = r.read()[:200].decode("utf-8", "ignore")
                code = r.status_code
                etype = "http_429" if code == 429 else f"http_{code}"
                return {"ok": False, "error_type": etype,
                        "detail": f"HTTP {code}: {body}"}
            for line in r.iter_lines():
                obj = _sse_obj(line)
                if not obj:
                    continue
                if obj.get("error"):
                    return {"ok": False, "error_type": "stream_error",
                            "detail": str(obj["error"])[:200]}
                choice = (obj.get("choices") or [{}])[0]
                delta = choice.get("delta") or {}
                for tc in delta.get("tool_calls") or []:
                    if ttft is None:
                        ttft = time.monotonic() - t0
                    slot = pending.setdefault(tc.get("index", 0),
                                              {"id": "", "name": "", "arguments": ""})
                    if tc.get("id"):
                        slot["id"] = tc["id"]
                    fn = tc.get("function") or {}
                    if fn.get("name"):
                        slot["name"] = fn["name"]
                    if fn.get("arguments"):
                        slot["arguments"] += fn["arguments"]
                if delta.get("content"):
                    if ttft is None:
                        ttft = time.monotonic() - t0
                    content += delta["content"]
            tool_calls = [{"name": pending[k]["name"],
                           "arguments": pending[k]["arguments"]}
                          for k in sorted(pending)]
            if not content.strip() and not tool_calls:
                return {"ok": False, "error_type": "empty",
                        "detail": "content 与 tool_calls 均为空"}
            return {"ok": True, "content": content,
                    "tool_calls": tool_calls,
                    "ttft_s": round(ttft, 3) if ttft is not None else None,
                    "latency_s": round(time.monotonic() - t0, 3),
                    "error_type": "none", "detail": ""}
    except httpx.TimeoutException:
        stream_broke = True
    except httpx.HTTPError as e:
        stream_broke = True
        detail = str(e)[:200]
    except Exception as e:  # noqa: BLE001
        stream_broke = True
        detail = str(e)[:200]
    if stream_broke:
        # 非流式回退（只兜流式链路故障，不影响已收到部分数据的成功请求）
        try:
            payload2 = {"messages": messages, "model": model["model_name"],
                        **model.get("extra_body", {})}
            if tools:
                payload2["tools"] = tools
            t1 = time.monotonic()
            r = httpx.post(endpoint, headers=headers, json=payload2,
                           timeout=model.get("timeout", 60))
            lat = round(time.monotonic() - t1, 3)
            if r.status_code >= 400:
                code = r.status_code
                etype = "http_429" if code == 429 else f"http_{code}"
                return {"ok": False, "error_type": etype, "detail": f"HTTP {code}"}
            msg = r.json()["choices"][0]["message"]
            if not (msg.get("content") or "").strip() and not msg.get("tool_calls"):
                return {"ok": False, "error_type": "empty", "detail": "空响应(非流式)"}
            return {"ok": True, "content": msg.get("content") or "",
                    "tool_calls": [{"name": (tc.get("function") or {}).get("name", ""),
                                    "arguments": (tc.get("function") or {}).get("arguments", "")}
                                   for tc in msg.get("tool_calls") or []],
                    "ttft_s": None, "latency_s": lat,
                    "error_type": "none", "detail": "非流式回退"}
        except httpx.TimeoutException:
            return {"ok": False, "error_type": "timeout", "detail": "非流式也超时"}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error_type": "network", "detail": str(e)[:200]}
    return {"ok": False, "error_type": "network", "detail": str(locals().get("detail", "unknown"))[:200]}


def call_with_retry(model, messages, tools, sys_fc):
    """重试规则（实验文档 5.3 冻结）：超时/瞬时网络错误重试 1 次；429 不重试。"""
    result = call_model_once(model, messages, tools, sys_fc)
    if not result["ok"] and result["error_type"] in ("timeout", "network"):
        result = call_model_once(model, messages, tools, sys_fc)
        result["detail"] = "(重试1次) " + result.get("detail", "")
    return result


# ---------- 评测主流程 ----------
def run(ability: str, model: dict, cases: list, rounds: int, out_csv: Path,
        sys_fc: str, fc_tools):
    ok = 0
    for case in cases:
        messages = [{"role": "system", "content": sys_fc}] if ability == "tool_use" else []
        messages.append({"role": "user", "content": case["utterance"]})
        tools = fc_tools if ability == "tool_use" else None
        for rnd in range(1, rounds + 1):
            result = call_with_retry(model, messages, tools, sys_fc)
            state = {"content": result.get("content", ""),
                     "tool_calls": result.get("tool_calls", [])}
            score, judge_ok, detail = (0.0, False, result.get("detail", ""))
            if result["ok"]:
                score, judge_ok, detail = judge_case(ability, case, state)
                ok += 1
            provider = f"{model.get('provider', 'unknown')}:{model['model_id']}"
            row = {"case_id": case["id"], "ability": ability,
                   "model_id": model["model_id"], "round": rnd,
                   "provider": provider, "ok": result["ok"],
                   "score": score, "judge_result": judge_ok,
                   "error_type": result.get("error_type", "judge"),
                   "ttft_s": result.get("ttft_s", ""),
                   "latency_s": result.get("latency_s", ""),
                   "resp_preview": (state.get("content") or str(state.get("tool_calls") or ""))[:200]}
            append_row(out_csv, row)
            mark = "PASS" if judge_ok else "FAIL"
            print(f"  [{model['model_id']}|{ability}] {case['id']} r{rnd} "
                  f"ok={result['ok']} {mark} score={score:.2f} {detail[:80]}")
    return ok


def append_row(out_csv: Path, row: dict):
    new_file = not out_csv.exists()
    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new_file:
            w.writeheader()
        w.writerow(row)


def main():
    ap = argparse.ArgumentParser(description="实验一：能力权重路由评测（单模型直连）")
    ap.add_argument("--ability", required=True,
                    help="chat / tool_use / code / reasoning / all")
    ap.add_argument("--model", required=True,
                    help="models.json 中的 model_id，或 all（遍历该能力全部有权重模型）")
    ap.add_argument("--rounds", type=int, default=3, help="每条用例重复轮次，默认 3")
    ap.add_argument("--limit", type=int, default=0, help="冒烟模式：仅取前 N 条用例")
    ap.add_argument("--out", default="", help="输出 CSV 路径，默认 test/results/raw.csv")
    ap.add_argument("--dry-run", action="store_true", help="只打印执行计划，不发请求")
    args = ap.parse_args()

    load_env()
    registry = load_registry()
    sys_fc = load_sys_fc()
    tool_reg = parse_tool_registry()
    fc_tools = build_fc_tools(tool_reg) if len(tool_reg) == 14 else None
    if fc_tools is None:
        print(f"[错误] 工具注册表解析到 {len(tool_reg)}/14 个，请检查 agent_service.py 格式")
        sys.exit(1)

    abilities = ABILITIES if args.ability == "all" else (args.ability,)
    out_csv = Path(args.out) if args.out else TEST_DIR / "results" / "raw.csv"
    tag = time.strftime("%Y%m%d_%H%M%S")
    print(f"评测计划：ability={args.ability} model={args.model} rounds={args.rounds} "
          f"limit={args.limit or '全部'} out={out_csv}")

    if args.dry_run:
        total = 0
        for ab in abilities:
            cases = json.loads((TEST_DIR / "cases" / f"{ab}.json").read_text("utf-8"))
            models = ([registry[args.model]] if args.model != "all"
                      else [m for m in registry.values() if m["ability_weights"].get(ab, 0) > 0])
            n = len(cases[:args.limit] if args.limit else cases)
            total += n * len(models) * args.rounds
            print(f"  {ab}: {n} 用例 × {len(models)} 模型 × {args.rounds} 轮")
        print(f"[dry-run] 共约 {total} 次请求，未发送。")
        return

    for ab in abilities:
        case_file = TEST_DIR / "cases" / f"{ab}.json"
        cases = json.loads(case_file.read_text("utf-8"))
        if args.limit:
            cases = cases[:args.limit]
        if args.model != "all":
            models = [registry[args.model]]
            if models[0]["ability_weights"].get(ab, 0) <= 0:
                print(f"[跳过] {args.model} 无 {ab} 能力权重")
                continue
        else:
            models = [m for m in registry.values() if m["ability_weights"].get(ab, 0) > 0]
        print(f"=== 能力 {ab}：{len(cases)} 用例 × {len(models)} 模型 ===")
        for m in models:
            if m.get("api_key_env") and not os.environ.get(m["api_key_env"]):
                print(f"[跳过] {m['model_id']}：环境变量 {m['api_key_env']} 未配置")
                continue
            run(ab, m, cases, args.rounds, out_csv, sys_fc, fc_tools)
    print(f"完成。原始数据：{out_csv}\n下一步：python {TEST_DIR / 'summarize.py'}")


if __name__ == "__main__":
    main()
