from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from Backend.database import Base

class User(Base):
    __tablename__ = "user"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(64), unique=True, nullable=False, index=True)
    email = Column(String(128), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    is_active = Column(Boolean, default=False)
    verify_token = Column(String(64), default="")
    reset_token = Column(String(64), default="")
    token_expires = Column(DateTime, nullable=True)
    session_token = Column(String(64), default="")
    session_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

