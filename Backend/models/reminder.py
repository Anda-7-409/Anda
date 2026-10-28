
from sqlalchemy import Column, Integer, String

from Backend.database import Base

class Reminder(Base):
    __tablename__ = "reminder"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)   
    reminder_type = Column(String(200), nullable=False)     
    reminder_time = Column(String(32), default="")          
    is_done = Column(Integer, default=0)                    
