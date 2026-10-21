# auth.py (用户认证) 用于用户登录注册、验证用户身份等操作
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()

class LoginRequest(BaseModel):
    username: str
    password: str

FAKE_USERS = {"admin": "123456"}

@router.post("/login")
def login(req: LoginRequest):
    if req.username not in FAKE_USERS:
        return JSONResponse(status_code=400, content={"code": 1, "message": "用户不存在", "data": None})
    if FAKE_USERS[req.username] != req.password:
        return JSONResponse(status_code=400, content={"code": 1, "message": "密码错误", "data": None})
    # TODO 第二步：真实 token（JWT）+ 查库验密（auth_service.py）
    return {"code": 0, "message": "登录成功", "data": {"token": "fake-token", "expires_in": 3600}}      