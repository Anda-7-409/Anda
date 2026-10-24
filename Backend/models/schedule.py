from sqlalchemy import Column, Integer, String
from Backend.database import Base

class Course(Base):
    __tablename__ = "course"
    # 用户课表：一人多课，user_id 隔离归属（与 Data/uploads/{user_id} 同思路）
    # weekday: 星期几（1=周一 … 7=周日）；start_slot/end_slot: 第几节课（1-12）
    # 字段名与前端 agent_ai.html 日程卡片契约一致（name/classroom/start_slot/end_slot/teacher）
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String(64), nullable=False)
    teacher = Column(String(32), default="")
    classroom = Column(String(64), default="")
    weekday = Column(Integer, nullable=False)
    start_slot = Column(Integer, nullable=False)
    end_slot = Column(Integer, nullable=False)