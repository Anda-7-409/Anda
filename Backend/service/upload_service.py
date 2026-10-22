# upload_service.py (上传模块业务) 格式/大小校验、防路径穿越、重名编号，统一落盘 Data/uploads/{user_id}/
import secrets
import time
from pathlib import Path

from Backend.config import UPLOAD_DIR

MAX_SIZE = 10 * 1024 * 1024  # 单文件上限 10MB（与前端 MAX_SIZE 保持一致）
ALLOWED_EXT = {"png", "jpg", "jpeg", "gif", "webp", "pdf", "doc", "docx",
               "xls", "xlsx", "ppt", "pptx", "txt", "md", "csv", "zip"}

def save_file(user_id: int, filename: str, content_type: str, content: bytes) -> dict:
    safe_name = Path(filename or "").name.strip()  # 只取文件名，防路径穿越
    if not safe_name:
        return {"ok": False, "message": "文件名不能为空哦~ ?-?"}
    ext = Path(safe_name).suffix.lower().lstrip(".")
    if ext not in ALLOWED_EXT:
        return {"ok": False, "message": f"暂不支持 .{ext or '未知'} 格式的文件哦 ^-v-"}
    if not content:
        return {"ok": False, "message": "文件是空的，是不是没选对呀 ~"}
    if len(content) > MAX_SIZE:
        return {"ok": False, "message": "文件超过 10MB 上限啦，压缩一下再传吧 ~"}

    user_dir = UPLOAD_DIR / str(user_id)
    user_dir.mkdir(parents=True, exist_ok=True)
    target = user_dir / safe_name
    if target.exists():  # 重名自动编号：课表.png → 课表(1).png
        i = 1
        while target.exists():
            target = user_dir / f"{Path(safe_name).stem}({i}).{ext}"
            i += 1
    target.write_bytes(content)

    return {"ok": True, "data": {
        "file_id": secrets.token_hex(8),
        "file_name": target.name,
        "size": len(content),
        "content_type": content_type or "application/octet-stream",
        # TODO: file_id → 路径 映射入库（upload 表），供后续 /download 与课表图片导入使用
    }}


def list_files(user_id: int) -> dict:
    # 列出当前用户已上传的文件（权限隔离：只读自己的目录），最新上传的排最前
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