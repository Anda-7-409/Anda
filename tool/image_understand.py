# image_understand.py — 图片理解：vision 能力权重链（glm-4.6V-Flash w10 → DeepSeek-OCR w7 → Qwen3.5-4B w6 → ...）
# 契约（docs/refactoring.md 3.2）：refs 为文件名列表，messages 里放 base64 图片，走 model_router.chat("vision")
import base64
from pathlib import Path

from AI import model_router, prompts
from Backend.service import upload_service

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
         ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}

def _ref_name(ref) -> str:
    # refs 条目兼容 dict（{file_name|name|filename}）与纯文件名两种形态（历史遗留的两种姿势，都得伺候 (。•́︿•̀。)）
    if isinstance(ref, dict):
        return (ref.get("file_name") or ref.get("name") or ref.get("filename") or "").strip()
    return str(ref or "").strip()

def image_understand_tool(utterance="", user_id=None, refs=None, **_) -> dict:
    # 只认本次引用里的图片文件；没有图片直接拒绝（防模型幻觉"看到"了不存在的东西——它真能睁眼说瞎话 (＞﹏＜)）
    for n in (_ref_name(r) for r in (refs or [])):
        if not n:
            continue
        info = upload_service.get_file_path(int(user_id), n) if user_id else {"ok": False}
        p = Path((info.get("data") or {}).get("path") or "")
        if p.suffix.lower() in _MIME and p.is_file():
            break
    else:
        return {"ok": False, "error": "嗷！本次对话里没有可识别的图片，请先上传一张图片再问我"}

    b64 = base64.b64encode(p.read_bytes()).decode()
    mime = _MIME[p.suffix.lower()]
    question = (utterance or "").strip() or prompts.P("image_understand.default_question")
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
        {"type": "text", "text": question},
    ]}]
    try:
        msg, provider = model_router.chat("vision", messages)
    except Exception as e:
        return {"ok": False, "error": "视觉模型暂时都不可用，请稍后再试", "hint": str(e)[:80]}
    answer = (msg or {}).get("content") or ""
    if not answer.strip():
        return {"ok": False, "error": "视觉模型没有返回内容，请换个问法或换一张图"}
    return {"ok": True, "image": p.name, "provider": provider, "answer": answer}
