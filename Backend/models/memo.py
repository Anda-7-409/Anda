
# memo.py (备忘录模型) 今日日程"+"添加的备忘录，落 app.db/memo 表，供前端展示与 AI 工具读取
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from Backend.database import Base

class Memo(Base):
    __tablename__ = "memo"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)   # 权限隔离：只看自己的备忘
    content = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
