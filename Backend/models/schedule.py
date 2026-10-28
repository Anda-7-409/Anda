from sqlalchemy import Column, Integer, String
from Backend.database import Base

class Course(Base):
    __tablename__ = "course"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    name = Column(String(64), nullable=False)
    teacher = Column(String(32), default="")
    classroom = Column(String(64), default="")
    weekday = Column(Integer, nullable=False)
    start_slot = Column(Integer, nullable=False)
    end_slot = Column(Integer, nullable=False)
