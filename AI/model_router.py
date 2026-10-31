# TODO: 以后部署添加日志记录
import json, os, logging, time
from pathlib import Path
import httpx

log = logging.getLogger("anda.router")
AI_DIR = Path(__file__).parent

_MODELS = {m["model_id"]: m for m in json.loads(
    (AI_DIR / "models.json").read_text("utf-8"))["models"]}

def _chain(ability: str):
    # 调用工具的权重进行调用模型，过滤掉权重为0,没有配置API的模型或者说没有这个能力的权重的模型
    ids = [m["model_id"] for m in sorted(
        _MODELS.values(), key=lambda m: -m["ability_weights"].get(ability, 0))]
    return [mid for mid in ids
            if (m := _MODELS[mid])["ability_weights"].get(ability, 0) > 0
            and (not m.get("api_key_env") or os.getenv(m["api_key_env"]))]

def chat(ability: str, messages: list, tools=None):
    # 返回 (message, provider)，全部失败时抛 NoModelError(路由层转错误码 11)
    for mid in _chain(ability):
        m = _MODELS[mid]
        headers = {"Authorization": f"Bearer {os.environ[m['api_key_env']]}"
                   } if m.get("api_key_env") else {}
        try:
            payload = {"messages": messages}
            if tools:
                payload["tools"] = tools
            r = httpx.post(m["endpoint"], headers=headers,
                           json={**payload, **m.get("extra_body", {}), "model": m["model_name"]},
                           timeout=m.get("timeout", 30))
            r.raise_for_status()
            msg = r.json()["choices"][0]["message"]
            # content或tool_calls任一返回即视为成功
            if (msg.get("content") or "").strip() or msg.get("tool_calls"):
                return msg, f"{m.get('provider', 'unknown')}:{mid}"
        except Exception as e:
            log.warning("嗷！%s 模型调用失败：%s", mid, e)
    raise NoModelError(ability)

def embed(texts: list):
    # 文本向量化：embeddings 端点与 chat 不同，按 embedding 权重滑链；
    # 返回与 texts 等长的向量列表，全部失败抛 NoModelError
    for mid in _chain("embedding"):
        m = _MODELS[mid]
        if not m["endpoint"].rstrip("/").endswith("embeddings"):
            continue
        headers = {"Authorization": f"Bearer {os.environ[m['api_key_env']]}"
                   } if m.get("api_key_env") else {}
        try:
            r = httpx.post(m["endpoint"], headers=headers,
                           json={"model": m["model_name"], "input": texts},
                           timeout=m.get("timeout", 30))
            r.raise_for_status()
            data = sorted(r.json()["data"], key=lambda d: d.get("index", 0))
            if len(data) != len(texts):
                continue
            return [d["embedding"] for d in data]
        except Exception as e:
            log.warning("嗷！嵌入模型 %s 也挂啦：-： %s", mid, e)
    raise NoModelError("embedding")

def transcribe(audio: bytes, filename="audio.wav"):
    # 语音转文字：audio/transcriptions 端点（multipart 上传，OpenAI whisper 兼容格式），
    # 按 asr 权重滑链，返回转写文本；全部失败抛 NoModelError
    for mid in _chain("asr"):
        m = _MODELS[mid]
        if not m["endpoint"].rstrip("/").endswith("transcriptions"):
            continue
        headers = {"Authorization": f"Bearer {os.environ[m['api_key_env']]}"
                   } if m.get("api_key_env") else {}
        try:
            r = httpx.post(m["endpoint"], headers=headers,
                           data={"model": m["model_name"]},
                           files={"file": (filename, audio)},
                           timeout=m.get("timeout", 100))
            r.raise_for_status()
            text = (r.json().get("text") or "").strip()
            if text:
                return text
        except Exception as e:
            log.warning("嗷！ASR模型 %s 挂啦 ：-： %s", mid, e)
    raise NoModelError("asr")

_probe_state = {}   # model_id -> {"ok": bool, "checked_at": "HH:MM:SS", "error": str}

def status():
    # /health 用：已探活模型返回最近一次真实探活结果，未探活模型退回配置检查
    out = {}
    for mid, m in _MODELS.items():
        configured = bool(not m.get("api_key_env") or os.getenv(m["api_key_env"]))
        entry = {"ok": configured, "checked_at": None}
        probe = _probe_state.get(mid)
        if probe:
            entry["ok"] = probe["ok"] and configured
            entry["checked_at"] = probe["checked_at"]
            if probe.get("error"):
                entry["error"] = probe["error"]
        out[mid] = entry
    return out

def probe_down():
    # 低频轻量探活：对已配置密钥的 chat 模型发 1-token 请求，结果写入 _probe_state 供 /health 展示；
    # 仅记录不熔断（真实调用的降级仍由 chat() 自身的滑链承担），探活失败不影响业务路由
    for mid, m in _MODELS.items():
        if not (m.get("api_key_env") and os.getenv(m["api_key_env"])):
            continue
        if m["ability_weights"].get("chat", 0) <= 0:
            continue
        ok, err = False, ""
        try:
            r = httpx.post(m["endpoint"],
                           headers={"Authorization": f"Bearer {os.environ[m['api_key_env']]}"},
                           json={"model": m["model_name"],
                                 "messages": [{"role": "user", "content": "hi"}],
                                 "max_tokens": 1},
                           timeout=8)
            ok = r.status_code < 400
            if not ok:
                err = f"HTTP {r.status_code}"
        except Exception as e:
            err = str(e)[:120]
        _probe_state[mid] = {"ok": ok, "checked_at": time.strftime("%H:%M:%S"), "error": err}

class NoModelError(Exception): pass

def _parse_sse_line(line: str):
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if data == "[DONE]":
        return None
    try:
        return json.loads(data)
    except Exception:
        return None

def chat_stream(ability: str, messages: list, tools=None):
    # 流式生成器，全部失败则降级使用非流式；带 tools 时支持 function calling：
    # 模型决定调工具时产出 {"type":"fc_tool_calls","calls":[{id,name,arguments}]}，
    # 由调用方执行工具后以 role:"tool" 回填消息再发起下一轮
    for mid in _chain(ability):
        m = _MODELS[mid]
        headers = {"Authorization": f"Bearer {os.environ[m['api_key_env']]}"
                   } if m.get("api_key_env") else {}
        payload = {"messages": messages, "stream": True, "model": m["model_name"],
                   **m.get("extra_body", {})}
        if tools:
            payload["tools"] = tools
        try:
            with httpx.stream("POST", m["endpoint"], headers=headers,
                              json=payload, timeout=m.get("stream_timeout", m.get("timeout", 30))) as r:
                r.raise_for_status()
                got = False
                pending = {}   # index -> {"id","name","arguments"}（流式 tool_calls 按 index 分片到达，需攒齐）
                yield {"type": "meta", "provider": f"{m.get('provider', 'unknown')}:{mid}"}
                for line in r.iter_lines():
                    obj = _parse_sse_line(line)
                    if not obj:
                        continue
                    if obj.get("error"):
                        # 流内错误：SSE建立连接后返回HTTP200，错误在data块
                        if got:
                            yield {"type": "error", "message": "回复中途被模型中断"}
                            return
                        break   # 如果首块前就报错则该模型失败
                    choice = (obj.get("choices") or [{}])[0]
                    delta = choice.get("delta") or {}
                    for tc in delta.get("tool_calls") or []:
                        got = True
                        slot = pending.setdefault(tc.get("index", 0),
                                                  {"id": "", "name": "", "arguments": ""})
                        if tc.get("id"):
                            slot["id"] = tc["id"]
                        fn = tc.get("function") or {}
                        if fn.get("name"):
                            slot["name"] = fn["name"]          # name 整体到达，直接覆盖
                        if fn.get("arguments"):
                            slot["arguments"] += fn["arguments"]   # arguments 分片追加
                    if delta.get("reasoning_content"):
                        got = True
                        yield {"type": "reasoning", "delta": delta["reasoning_content"]}
                    if delta.get("content"):
                        got = True
                        yield {"type": "content", "delta": delta["content"]}
                if pending:
                    yield {"type": "fc_tool_calls", "calls": [pending[i] for i in sorted(pending)]}
                    return
                if got:
                    return
        except Exception as e:
            log.warning("嗷！%s 流式调用失败：%s", mid, e)
    # 如果全部流式失败则采用非流式
    try:
        msg, provider = chat(ability, messages, tools)
        yield {"type": "meta", "provider": provider}
        if msg.get("tool_calls"):
            yield {"type": "fc_tool_calls", "calls": [
                {"id": tc.get("id", ""), "name": (tc.get("function") or {}).get("name", ""),
                 "arguments": (tc.get("function") or {}).get("arguments")}
                for tc in msg["tool_calls"]]}
        else:
            yield {"type": "content", "delta": msg.get("content") or ""}
    except Exception as e:
        log.warning("stream fallback failed: %s", e)