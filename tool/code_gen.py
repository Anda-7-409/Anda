# code_gen.py — 代码生成：code 能力权重链（DeepSeek-R1-Qwen3-8B w10 → GLM-4-9B w9 → ...）
# 契约（docs/refactoring.md 3.2）：model_router.chat("code")；产物存用户云盘，经 /upload/download 下载
import time

from AI import model_router, prompts
from Backend import config
from Backend.service import upload_service

_EXT = {"python": "py", "py": "py", "javascript": "js", "js": "js", "typescript": "ts",
        "ts": "ts", "html": "html", "css": "css", "java": "java", "c": "c", "cpp": "cpp",
        "c++": "cpp", "golang": "go", "go": "go", "sql": "sql", "shell": "sh", "bash": "sh",
        "json": "json"}

def _extract(text: str) -> tuple:
    # 从模型输出中取第一个 ```语言 围栏内的代码；无围栏时整体视为代码（默认 .py）
    start = text.find("```")
    if start == -1:
        return text.strip(), "py"
    rest = text[start + 3:]
    nl = rest.find("\n")
    tag = (rest[:nl] if nl != -1 else "").strip().lower() or "python"
    end = rest.find("```", nl + 1 if nl != -1 else 0)
    body = rest[(nl + 1) if nl != -1 else 0: end if end != -1 else None]
    return body.strip(), _EXT.get(tag, "py")

def code_gen_tool(utterance="", user_id=None, refs=None, **_) -> dict:
    task = (utterance or "").strip()
    if not task:
        return {"ok": False, "error": "没有描述要生成什么代码"}
    try:
        msg, provider = model_router.chat("code", [{"role": "user", "content":
            prompts.P("code_gen.user", task=task)}])
    except Exception as e:
        return {"ok": False, "error": "代码模型暂时都不可用，请稍后再试", "hint": str(e)[:80]}
    code, ext = _extract((msg or {}).get("content") or "")
    if not code.strip():
        return {"ok": False, "error": "模型没有返回有效代码，请把需求描述得更具体一点"}

    name = f"anda_code_{int(time.time())}.{ext}"
    up = upload_service.save_file(int(user_id or 0), name, "text/plain", code.encode("utf-8"))
    if not up.get("ok"):
        return {"ok": False, "error": "代码文件保存失败：" + str(up.get("message") or "")}
    real = up["data"]["file_name"]   # save_file 重名时会加 (1) 后缀，用最终名拼链接
    return {"ok": True, "file_name": real, "lines": code.count("\n") + 1,
            "download_url": f"{config.FRONTEND_BASE_URL}/upload/download/{real}",
            "code_preview": code[:200], "provider": provider,
            "hint": "文件已保存到用户云盘，可在左侧文件管理器下载"}
