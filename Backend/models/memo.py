
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from Backend.database import Base

class Memo(Base):
    __tablename__ = "memo"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)   
    content = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
