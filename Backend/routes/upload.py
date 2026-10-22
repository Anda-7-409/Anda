# upload.py (上传模块) 对应 plan.md 第8节 POST /upload → 落盘 Data/uploads/{user_id}，返回 file_id
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from Backend.models.user import User
from Backend.service import auth_service, upload_service

router = APIRouter()

@router.post("/")
async def upload(
    file: UploadFile = File(...),
    user: User = Depends(auth_service.get_current_user),
):
    # 路由层只负责收发：读文件 → 交给 service 校验落盘 → 统一 {code,message,data} 封装
    content = await file.read()
    result = upload_service.save_file(user.id, file.filename or "", file.content_type, content)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"code": 1, "message": result["message"], "data": None})
    return {"code": 0, "message": "ok", "data": result["data"]}


@router.get("/")
def list_uploaded_files(user: User = Depends(auth_service.get_current_user)):
    # 文件管理器数据源：只返回当前登录用户自己的文件（按上传时间倒序）
    result = upload_service.list_files(user.id)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"code": 1, "message": result["message"], "data": None})
    return {"code": 0, "message": "ok", "data": result["data"]}


@router.get("/download/{filename}")
def download_file(filename: str, user: User = Depends(auth_service.get_current_user)):
    # 下载/预览统一走这里：前端用 fetch 带 Authorization 取回二进制（img/iframe 标签带不了请求头）
    result = upload_service.get_file_path(user.id, filename)
    if not result["ok"]:
        return JSONResponse(status_code=404, content={"code": 1, "message": result["message"], "data": None})
    d = result["data"]
    return FileResponse(d["path"], filename=d["file_name"])