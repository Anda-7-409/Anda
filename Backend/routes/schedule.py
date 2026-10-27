from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from Backend.database import get_db
from Backend.models.user import User
from Backend.service import auth_service, schedule_service

router = APIRouter()

class CourseCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=64)
    teacher: str = ""
    classroom: str = ""
    weekday: int = Field(..., ge=1, le=7)
    start_slot: int = Field(..., ge=1, le=12)
    end_slot: int = Field(..., ge=1, le=12)

def _ok(data):
    return {"code": 0, "message": "ok", "data": data}

def _fail(message: str, status: int = 400):
    return JSONResponse(status_code=status, content={"code": 1, "message": message, "data": None})

@router.get("/today")
def get_today(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    return _ok(schedule_service.today_courses(db, user.id)["data"])

@router.get("/courses")
def get_courses(user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    return _ok(schedule_service.week_courses(db, user.id)["data"])

@router.post("/courses")
def add_course(req: CourseCreate, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = schedule_service.add_course(db, user.id, req)
    if not result["ok"]:
        return _fail(result["message"])
    return _ok(result["data"])

@router.delete("/courses/{course_id}")
def delete_course(course_id: int, user: User = Depends(auth_service.get_current_user), db: Session = Depends(get_db)):
    result = schedule_service.delete_course(db, user.id, course_id)
    if not result["ok"]:
        return _fail(result["message"], status=404 if "不存在" in result["message"] else 400)
    return _ok(result["data"])
