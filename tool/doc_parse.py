
# tool/doc_parse.py (文档解析工具链) Agent 可调用的文档理解：MinerU 双路径解析

# 配了 MINERU_API_KEY → 精准解析 API（≤200MB/600页，vlm 模型，结果 zip 内取 full.md）

# 没配 Key → Agent 轻量解析 API（免登录 IP 限频，≤10MB/20页，直接返回 Markdown 链接）

# 异步链路：提交任务 → 有界轮询 → 下载 Markdown；超时/失败返回结构化错误，AI 不得编造内容
import io
import re
import time
import zipfile
from pathlib import Path

import requests

from Backend.config import (DOC_PARSE_MAX_WAIT_SECONDS, MINERU_API_KEY, MINERU_MODEL,
                            UPLOAD_DIR)

BASE = "https://mineru.net"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
POLL_INTERVAL = 3        # 秒：轮询间隔
MAX_CHARS = 6000         # 注入对话的 Markdown 上限：够 AI 总结，又不撑爆提示词
SUPPORTED_EXT = {"pdf", "doc", "docx", "ppt", "pptx", "xls", "xlsx", "html",
                 "png", "jpg", "jpeg", "webp", "gif", "bmp", "jp2"}
_URL_RE = re.compile(r"https?://\S+")

def _auth() -> dict:
    return {"Authorization": f"Bearer {MINERU_API_KEY}", "Content-Type": "application/json"}

# ===== 精准解析 API（需 Token；URL 单文件 / 本地文件走批量上传）=====
def _submit_url(url: str) -> str:
    resp = requests.post(f"{BASE}/api/v4/extract/task", headers=_auth(),
                         json={"url": url, "model_version": MINERU_MODEL}, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(body.get("msg") or "创建解析任务失败")
    return (body.get("data") or {}).get("task_id") or ""

def _submit_file(name: str, content: bytes) -> str:
    # 批量接口单文件也走它：申请上传链接 → PUT 文件 → 系统自动提交解析
    resp = requests.post(f"{BASE}/api/v4/file-urls/batch", headers=_auth(),
                         json={"files": [{"name": name}], "model_version": MINERU_MODEL},
                         timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(body.get("msg") or "申请上传链接失败")
    data = body.get("data") or {}
    upload_url = (data.get("file_urls") or [""])[0]
    if not upload_url:
        raise RuntimeError("未获取到上传链接")
    put = requests.put(upload_url, data=content, timeout=120)   # 上传无须 Content-Type
    put.raise_for_status()
    return data.get("batch_id") or ""

def _poll_task(task_id: str) -> str:
    # 单文件任务轮询：done → full_zip_url，failed → 抛出官方 err_msg
    if not task_id:
        raise RuntimeError("未获取到任务ID")
    deadline = time.time() + DOC_PARSE_MAX_WAIT_SECONDS
    while time.time() < deadline:
        resp = requests.get(f"{BASE}/api/v4/extract/task/{task_id}", headers=_auth(), timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        if data.get("state") == "done":
            return data.get("full_zip_url") or ""
        if data.get("state") == "failed":
            raise RuntimeError(data.get("err_msg") or "解析失败")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError("解析超时")

def _poll_batch(batch_id: str) -> str:
    # 批量任务轮询：只取第一个文件的结果（本工具一次只解析一个）
    if not batch_id:
        raise RuntimeError("未获取到任务ID")
    deadline = time.time() + DOC_PARSE_MAX_WAIT_SECONDS
    while time.time() < deadline:
        resp = requests.get(f"{BASE}/api/v4/extract-results/batch/{batch_id}",
                            headers=_auth(), timeout=15)
        resp.raise_for_status()
        results = (resp.json().get("data") or {}).get("extract_result") or []
        r = results[0] if results else {}
        if r.get("state") == "done":
            return r.get("full_zip_url") or ""
        if r.get("state") == "failed":
            raise RuntimeError(r.get("err_msg") or "解析失败")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError("解析超时")

def _zip_to_markdown(zip_url: str) -> str:
    # 结果是 zip 包，解出 full.md（Markdown 全文）；result_url 留着 zip 链接供用户下载完整结果
    resp = requests.get(zip_url, timeout=120)
    resp.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        md = next((n for n in zf.namelist() if n.endswith("full.md")), None)
        if not md:
            raise RuntimeError("解析结果包里没有 full.md")
        return zf.read(md).decode("utf-8", errors="ignore")

# ===== Agent 轻量解析 API（免登录；直接返回 Markdown 链接）=====
def _agent_poll(task_id: str) -> str:
    if not task_id:
        raise RuntimeError("未获取到任务ID")
    deadline = time.time() + DOC_PARSE_MAX_WAIT_SECONDS
    while time.time() < deadline:
        resp = requests.get(f"{BASE}/api/v1/agent/parse/{task_id}", timeout=15)
        resp.raise_for_status()
        data = resp.json().get("data") or {}
        if data.get("state") == "done":
            return data.get("markdown_url") or ""
        if data.get("state") == "failed":
            raise RuntimeError(data.get("err_msg") or "解析失败")
        time.sleep(POLL_INTERVAL)
    raise TimeoutError("解析超时")

def _download(url: str) -> str:
    if not url:
        raise RuntimeError("解析完成但没拿到结果链接")
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=60)
    resp.raise_for_status()
    return resp.text

# ===== 统一入口：按是否配了 Key 自动选路径，对外契约不变 =====
def parse(url: str = "", file_name: str = "", file_content: bytes = b"") -> dict:
    if not url and not file_name:
        return {"ok": False, "error": "没拿到文档地址或文件"}
    result_url = ""
    try:
        if MINERU_API_KEY:   # 精准解析：精度更高、限额更大，结果在 zip 里
            zip_url = _poll_task(_submit_url(url)) if url \
                else _poll_batch(_submit_file(file_name, file_content))
            if not zip_url:
                raise RuntimeError("解析完成但没拿到结果包地址")
            markdown, result_url = _zip_to_markdown(zip_url), zip_url
        else:                # 轻量解析（免登录）：Markdown 链接直出
            markdown = _download(_agent_poll(_agent_url(url))) if url \
                else _download(_agent_poll(_agent_file(file_name, file_content)))
    except TimeoutError:
        return {"ok": False, "error": "解析超时，文档可能太长",
                "note": "稍后重试或换小一点的文件"}
    except Exception as exc:
        return {"ok": False, "error": f"解析失败：{str(exc)[:120]}"}
    markdown = (markdown or "").strip()
    if not markdown:
        return {"ok": False, "error": "解析完成但文档内容为空"}
    truncated = len(markdown) > MAX_CHARS
    return {"ok": True, "file_name": file_name or url, "total_chars": len(markdown),
            "truncated": truncated, "result_url": result_url,
            "content": markdown[:MAX_CHARS] + ("…（已截断）" if truncated else "")}

def _agent_url(url: str) -> str:
    resp = requests.post(f"{BASE}/api/v1/agent/parse/url", json={"url": url}, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(body.get("msg") or "创建解析任务失败")
    return (body.get("data") or {}).get("task_id") or ""

def _agent_file(name: str, content: bytes) -> str:
    # 免登录上传：先拿一次性上传链接，PUT 文件后系统自动提交解析
    resp = requests.post(f"{BASE}/api/v1/agent/parse/file",
                         json={"file_name": name}, timeout=15)
    resp.raise_for_status()
    body = resp.json()
    if body.get("code") != 0:
        raise RuntimeError(body.get("msg") or "申请上传链接失败")
    data = body.get("data") or {}
    upload_url = data.get("file_url") or ""
    if not upload_url:
        raise RuntimeError("未获取到上传链接")
    put = requests.put(upload_url, data=content, timeout=120)
    put.raise_for_status()
    return data.get("task_id") or ""

# ===== 工具入口：从话术里找文档链接或用户已上传的文件 =====
def doc_parse_tool(utterance: str, user_id: int, refs=None) -> dict:
    text = utterance or ""
    m = _URL_RE.search(text)
    if m:
        return _wrap(parse(url=m.group(0).rstrip("，。！？!?、)）")))
    # 只读用户自己的上传目录（权限隔离，复用 upload 模块目录结构）
    user_dir = UPLOAD_DIR / str(user_id)
    files = sorted((p for p in user_dir.iterdir() if p.is_file()
                    and p.suffix.lower().lstrip(".") in SUPPORTED_EXT),
                   key=lambda p: p.stat().st_mtime, reverse=True) if user_dir.exists() else []
    by_name = {p.name: p for p in files}
    ref_hits = [by_name[str(r)] for r in (refs or []) if str(r) in by_name]   # @引用的且确实可解析
    mentioned = [p for p in files if p.name in text or Path(p.name).stem in text]
    if len(ref_hits) == 1:          # ① 用户显式 @ 引用 → 最强信号，直接用（引用图片等非文档时 ref_hits 为空，走后面逻辑）
        target = ref_hits[0]
    elif len(ref_hits) > 1:         # 引用了多个可解析文档且没点名 → 追问
        return {"ok": False, "error": "你引用了多个文档，但没说清要解析哪个",
                "candidates": [p.name for p in ref_hits], "hint": "列出候选让用户选"}
    elif len(mentioned) == 1:       # ② 正文点名了文件名
        target = mentioned[0]
    elif len(mentioned) > 1:
        return {"ok": False, "error": "提到多个文件，不确定解析哪一个",
                "candidates": [p.name for p in mentioned], "hint": "追问用户要解析哪个文件"}
    elif len(files) == 1:
        target = files[0]   # “解析这个PDF”没点名 → 只有唯一可解析文件时直接用
    elif files:
        return {"ok": False, "error": "你上传了多个文档，但没说清要解析哪个",
                "candidates": [p.name for p in files[:8]], "hint": "列出候选让用户选"}
    else:
        return {"ok": False, "error": "没找到要解析的文档",
                "hint": "请用户先上传文档，或直接给出文档链接"}
    content = target.read_bytes()
    if len(content) > 10 * 1024 * 1024 and not MINERU_API_KEY:
        return {"ok": False, "error": f"文件 {target.name} 超过 10MB，免登录轻量解析带不动",
                "hint": "提示用户配置 MINERU_API_KEY 后可解析最大 200MB 的文件"}
    return _wrap(parse(file_name=target.name, file_content=content))

def _wrap(got: dict) -> dict:
    if not got["ok"]:
        return {"ok": False, "error": got["error"],
                "hint": got.get("note", "如实告知用户解析失败原因，不要编造文档内容")}
    return {"query": got["file_name"], "total_chars": got["total_chars"],
            "truncated": got["truncated"], "content": got["content"],
            "result_url": got["result_url"] or None,
            "note": "必须基于以上真实解析内容作答，引用时注明出自文档哪部分；内容里没有的不要编"}
