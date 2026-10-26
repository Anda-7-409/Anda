# nav.py (导航路由) 位置上报 + 路线规划；只收参与封装，业务在 nav_service
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from Backend.models.user import User
from Backend.service import auth_service, nav_service

router = APIRouter()

class LocationIn(BaseModel):
    lng: float = Field(..., ge=-180, le=180)
    lat: float = Field(..., ge=-90, le=90)

class PlanIn(BaseModel):
    target: str = Field(..., min_length=1, max_length=100)
    mode: str = Field(default="walk", pattern="^(walk|ride|drive)$")
    origin: Optional[LocationIn] = None

def _ok(data):
    return {"code": 0, "message": "ok", "data": data}

def _fail(message: str):
    return JSONResponse(status_code=400, content={"code": 1, "message": message, "data": None})

@router.post("/location")
def report_location(req: LocationIn, user: User = Depends(auth_service.get_current_user)):
    # 前端点"导航"时上报浏览器定位；30 分钟内规划路线可直接复用
    nav_service.update_location(user.id, req.lng, req.lat)
    return _ok({"saved": True})

@router.post("/plan")
def plan(req: PlanIn, user: User = Depends(auth_service.get_current_user)):
    result = nav_service.plan(user.id, req.target, req.mode,
                              origin=f"{req.origin.lng},{req.origin.lat}" if req.origin else "")
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["data"])
