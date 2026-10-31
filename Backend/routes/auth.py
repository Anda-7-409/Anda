# auth路由，从index接入，传到auth_service
from typing import Optional

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel 
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service

router = APIRouter()
# 方便AI或IDE进行代码补全 -w-
# str 是必填的 str = "" 可选 Optional[str] = None 不传则None
class Register_must(BaseModel):
    username: str
    password: str
    email: str

# 缺少必填项,经过fastapi时触发422错误（422 这位不速之客，fastapi 替咱把关 (。•́︿•̀。)）
class Login_must(BaseModel):
    username: str
    password: str


class Forgot_password_must(BaseModel):
    email: str


class Reset_password_must(BaseModel):
    token: str
    new_password: str


class Update_must(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


def _ok(message="ok", data=None):
    return {"code": 0, "message": message, "data": data}


def _fail(message, status=400):
    return JSONResponse(status_code=status, content={"code": 1, "message": message, "data": None})


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else ""


@router.post("/register")
def register(req: Register_must, request: Request, db: Session = Depends(get_db)):
    result = auth_service.register_user(db, req.username, req.password, req.email, client_ip=_client_ip(request))
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])


@router.get("/verify")
def verify(token: str, db: Session = Depends(get_db)):
    ok = auth_service.verify_user(db, token)
    return RedirectResponse(url=f"/index.html?verify={'ok' if ok else 'fail'}", status_code=302)



@router.post("/login")
def login(req: Login_must, request: Request, db: Session = Depends(get_db)):
    result = auth_service.login(db, req.username, req.password, client_ip=_client_ip(request))
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"], {"token": result["token"], "expires_in": result["expires_in"]})


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    auth_service.logout_user(db, authorization)
    return _ok("已退出登录")


@router.get("/me")
def me(user: User = Depends(auth_service.get_current_user)):
    # 查头比token，判断是否过期
    return _ok(data={"user_id": user.id, "username": user.username, "email": user.email})


@router.put("/update")
def update(
    req: Update_must,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    result = auth_service.update_profile(db, user, req.username, req.email, req.password)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])


@router.post("/forgot_password")
def forgot_password(req: Forgot_password_must, request: Request, db: Session = Depends(get_db)):
    result = auth_service.forgot_password(db, req.email, client_ip=_client_ip(request))
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])


@router.post("/reset_password")
def reset_password(req: Reset_password_must, db: Session = Depends(get_db)):
    result = auth_service.reset_password(db, req.token, req.new_password)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])
