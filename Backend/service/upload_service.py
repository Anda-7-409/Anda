
import logging
import secrets
import time
import uuid
from pathlib import Path

from Backend.config import UPLOAD_DIR

log = logging.getLogger("anda.upload")

MAX_SIZE = 10 * 1024 * 1024  
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "doc", "docx",
               "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "zip",
               # 代码文件（code_gen 产物落云盘用；只存不执行，无注入风险——放心，咱不养蛊 (¬‿¬)）
               "py", "js", "ts", "java", "c", "cpp", "go", "sql", "sh", "html", "css", "json"}

def save_file(user_id: int, filename: str, content_type: str, content: bytes) -> dict:
    safe_name = Path(filename or "").name.strip()  
    if not safe_name:
        return {"ok": False,"code": 40, "message": "文件名不能为空哦 (。•́︿•̀。) 文件总得有个名字嘛~"}
    ext = Path(safe_name).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXT:
        return {"ok": False,"code": 41, "message": f"暂不支持 .{ext or '未知'} 格式的文件哦 (＞﹏＜) 换个格式试试~"}
    if not content:
        return {"ok": False,"code": 42, "message": "文件是空的，是不是没选对呀 (´･ω･`)"}
    if len(content) > MAX_SIZE:
        return {"ok": False,"code": 43, "message": "文件超过 10MB 上限啦，营养过剩了，压缩一下再喂我吧 (＞﹏＜)"}

    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    # uuid 短后缀：同名文件并发上传也各存各的，不存在"exists 判断-写入"竞态覆盖问题（TOCTOU 这坑，摔一次记一辈子 (。•́︿•̀。)）
    target = user_dir / f"{Path(safe_name).stem}-{uuid.uuid4().hex[:8]}.{ext}"
    target.write_bytes(content)
    log.info("文件上传 -> user_id=%s file=%s（%.1f KB）(๑•̀ㅂ•́)و✧", user_id, target.name, len(content) / 1024)

    return {"ok": True, "data": {
        "file_id": secrets.token_hex(8),
        "file_name": target.name,
        "size": len(content),
        "content_type": content_type or "application/octet-stream",
    }}


def list_files(user_id: int) -> dict:
    user_dir = UPLOAD_DIR / str(user_id)
    if not user_dir.exists():
        return {"ok": True, "data": []}
    entries = [p for p in user_dir.iterdir() if p.is_file()]
    entries.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    files = [{
        "file_name": p.name,
        "size": p.stat().st_size,
        "ext": p.suffix.lower().lstrip("."),
        "uploaded_at": time.strftime("%Y-%m-%d %H:%M", time.localtime(p.stat().st_mtime)),
    } for p in entries]
    return {"ok": True, "data": files}


def get_file_path(user_id: int, filename: str) -> dict:
    safe_name = Path(filename or "").name.strip()  
    if not safe_name:
        return {"ok": False,"code": 40, "message": "文件名不能为空哦 (。•́︿•̀。) 文件总得有个名字嘛~"}
    target = UPLOAD_DIR / str(user_id) / safe_name
    if not target.is_file():
        return {"ok": False,"code": 45, "message": "文件不存在，或者已经被删掉啦 (´•̥ω•̥`)"}
    return {"ok": True, "data": {"path": target, "file_name": safe_name}}


def delete_file(user_id: int, filename: str) -> dict:
    got = get_file_path(user_id, filename)
    if not got["ok"]:
        return got
    try:
        got["data"]["path"].unlink()
    except Exception as exc:
        log.warning("文件删除失败 -> user_id=%s file=%s：%s (＞﹏＜)", user_id, filename, exc)
        return {"ok": False,"code": 44, "message": f"删除失败了 (╯°□°）╯︵ ┻━┻ {exc}"}
    log.info("文件删除 -> user_id=%s file=%s ヾ(≧▽≦*)o", user_id, got["data"]["file_name"])
    return {"ok": True, "data": {"file_name": got["data"]["file_name"]}}