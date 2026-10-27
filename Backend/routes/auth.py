from typing import Optional

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service

router = APIRouter()

class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str



class LoginRequest(BaseModel):
    username: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class UpdateRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None


def _ok(message="ok", data=None):
    return {"code": 0, "message": message, "data": data}


def _fail(message, status=400):
    return JSONResponse(status_code=status, content={"code": 1, "message": message, "data": None})


@router.post("/register")
def register(req: RegisterRequest, db: Session = Depends(get_db)):
    result = auth_service.register_user(db, req.username, req.password, req.email)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])


@router.get("/verify")
def verify(token: str, db: Session = Depends(get_db)):
    ok = auth_service.verify_user(db, token)
    return RedirectResponse(url=f"/index.html?verify={'ok' if ok else 'fail'}", status_code=302)



@router.post("/login")
def login(req: LoginRequest, db: Session = Depends(get_db)):
    result = auth_service.login(db, req.username, req.password)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"], {"token": result["token"], "expires_in": result["expires_in"]})


@router.post("/logout")
def logout(authorization: Optional[str] = Header(default=None), db: Session = Depends(get_db)):
    auth_service.logout_user(db, authorization)
    return _ok("已退出登录")


@router.get("/me")
def me(user: User = Depends(auth_service.get_current_user)):
    return _ok(data={"user_id": user.id, "username": user.username, "email": user.email})


@router.put("/update")
def update(
    req: UpdateRequest,
    user: User = Depends(auth_service.get_current_user),
    db: Session = Depends(get_db),
):
    result = auth_service.update_profile(db, user, req.username, req.email, req.password)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])


@router.post("/forgot-password")
def forgot_password(req: ForgotPasswordRequest, db: Session = Depends(get_db)):
    result = auth_service.forgot_password(db, req.email)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])


@router.post("/reset-password")
def reset_password(req: ResetPasswordRequest, db: Session = Depends(get_db)):
    result = auth_service.reset_password(db, req.token, req.new_password)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["message"])
