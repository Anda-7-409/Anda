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
    verify_expires = Column(DateTime, nullable=True)   # 激活链接独立过期，与重置链路解耦
    reset_expires = Column(DateTime, nullable=True)    # 重置链接独立过期，避免旧激活链接被"续命"
    session_token = Column(String(64), default="")     # 仅存 SHA-256 摘要，明文不落库
    session_expires = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

