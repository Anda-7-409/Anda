from datetime import datetime
from sqlalchemy import Boolean, Column, DateTime, Integer, String
from Backend.database import Base

class User(Base):
    __tablename__ = "user"
    # 定义用户表的字段
    # id: 主键，自增
    # username: 用户名，唯一，索引
    # email: 邮箱，唯一，索引
    # password_hash: 密码哈希，必填（存PBKDF2哈希，绝不存明文）
    # is_active: 是否激活，默认 False
    # verify_token: 验证令牌，默认空字符串
    # reset_token: 重置密码令牌，默认空字符串
    # token_expires: 令牌过期时间，默认 None
    # session_token: 会话令牌，默认空字符串
    # session_expires: 会话过期时间，默认 None
    # created_at: 创建时间，默认当前时间
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

