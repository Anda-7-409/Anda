
# tool/image_understand.py (图片理解工具链) Agent 可调用的看图说话：视觉模型槽（GLM-4.6V）

# 图片理解走多模态模型而非 MinerU OCR：OCR 只能抠字，视觉模型才能回答“图里有什么/画的是什么”

# 图片来源：话术中的图片链接，或用户已上传的最新图片（uploads/{user_id}/，权限隔离）
import base64
import re
from pathlib import Path

import requests

from AI import glm
from Backend.config import GLM_API_KEY, GLM_MODEL_VISION, UPLOAD_DIR

MAX_BYTES = 5 * 1024 * 1024   # 视觉模型对超大图识别质量下降，5MB 以内为佳
IMG_EXT = {"png", "jpg", "jpeg", "webp", "gif", "bmp"}
_MIME = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
         "webp": "image/webp", "gif": "image/gif", "bmp": "image/bmp"}
_URL_RE = re.compile(r"https?://\S+")

def _ask_vision(question: str, image_b64: str, mime: str) -> str:
    # GLM 多模态消息格式：content 是数组，图片用 data URI 内嵌 base64，复用 glm.chat 发请求
    messages = [{
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{image_b64}"}},
            {"type": "text", "text": f"用户的问题：{question}\n\n请基于图片真实内容回答；图片里没有的信息不要编造。"},
        ],
    }]
    return glm.chat(messages, model=GLM_MODEL_VISION)

def image_understand_tool(utterance: str, user_id: int, refs=None) -> dict:
    if not GLM_API_KEY or not GLM_MODEL_VISION:
        return {"ok": False, "error": "未配置视觉模型（GLM_API_KEY / GLM_MODEL_PICTURE_UNDERSTAND）",
                "hint": "如实告知用户图片理解功能暂不可用，不要编造图片内容"}
    text = utterance or ""
    data = b""
    name = ""
    m = _URL_RE.search(text)
    if m and Path(m.group(0).split("?")[0]).suffix.lower().lstrip(".") in IMG_EXT:
        url = m.group(0).rstrip("，。！？!?、)）")
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
        except Exception as exc:
            return {"ok": False, "error": f"图片下载失败：{str(exc)[:80]}"}
        data, name = resp.content, Path(url).name
    else:
        user_dir = UPLOAD_DIR / str(user_id)   # 只读用户自己的上传目录（权限隔离）
        imgs = sorted((p for p in user_dir.iterdir()
                       if p.is_file() and p.suffix.lower().lstrip(".") in IMG_EXT),
                      key=lambda p: p.stat().st_mtime, reverse=True) if user_dir.exists() else []
        mentioned = [p for p in imgs if p.name in text or p.stem in text]
        ref_hits = [p for p in imgs if p.name in (refs or [])]   # @引用的且确实是图片
        if len(ref_hits) == 1:
            target = ref_hits[0]          # ① 显式引用 → 最强信号（引用的是文档时 ref_hits 为空，走后面逻辑）
        elif len(ref_hits) > 1:
            return {"ok": False, "error": "你引用了多张图片，但没说清要看哪张",
                    "candidates": [p.name for p in ref_hits], "hint": "列出候选让用户选"}
        elif len(mentioned) > 1:
            return {"ok": False, "error": "提到多张图片，不确定看哪张",
                    "candidates": [p.name for p in mentioned], "hint": "追问用户要看哪一张"}
        elif mentioned:
            target = mentioned[0]         # ② 正文点名了图片
        else:
            target = imgs[0] if imgs else None   # ③ 没点名 → 只有一张或取最新
        if target is None:
            return {"ok": False, "error": "没找到要看的图片",
                    "hint": "请用户先上传图片，或直接给出图片链接"}
        data, name = target.read_bytes(), target.name
    ext = Path(name).suffix.lower().lstrip(".")
    if len(data) > MAX_BYTES:
        return {"ok": False, "error": f"图片 {name} 超过 5MB，视觉模型看不动",
                "hint": "提示用户压缩后再上传"}
    answer = _ask_vision(text, base64.b64encode(data).decode(), _MIME.get(ext, "image/png"))
    if not answer:
        return {"ok": False, "error": "视觉模型暂时不可用",
                "hint": "如实告知用户稍后再试，不要编造图片内容"}
    return {"ok": True, "image": name, "answer": answer,
            "note": "以上是视觉模型对图片的真实描述，直接转述即可，不要额外编造细节"}
