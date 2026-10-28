
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
    content = await file.read()
    result = upload_service.save_file(user.id, file.filename or "", file.content_type, content)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"code": 1, "message": result["message"], "data": None})
    return {"code": 0, "message": "ok", "data": result["data"]}


@router.get("/")
def list_uploaded_files(user: User = Depends(auth_service.get_current_user)):
    result = upload_service.list_files(user.id)
    if not result["ok"]:
        return JSONResponse(status_code=400, content={"code": 1, "message": result["message"], "data": None})
    return {"code": 0, "message": "ok", "data": result["data"]}


@router.get("/download/{filename}")
def download_file(filename: str, user: User = Depends(auth_service.get_current_user)):
    result = upload_service.get_file_path(user.id, filename)
    if not result["ok"]:
        return JSONResponse(status_code=404, content={"code": 1, "message": result["message"], "data": None})
    d = result["data"]
    return FileResponse(d["path"], filename=d["file_name"])


@router.delete("/{filename}")
def delete_uploaded_file(filename: str, user: User = Depends(auth_service.get_current_user)):
    result = upload_service.delete_file(user.id, filename)
    if not result["ok"]:
        status = 404 if "不存在" in result["message"] else 400
        return JSONResponse(status_code=status, content={"code": 1, "message": result["message"], "data": None})
    return {"code": 0, "message": "ok", "data": result["data"]}
