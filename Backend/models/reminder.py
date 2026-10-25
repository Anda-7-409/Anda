
# reminder.py (提醒模型) 到点提醒落 app.db/reminder 表；字段名对齐 plan.md /reminder 契约
from sqlalchemy import Column, Integer, String

from Backend.database import Base

class Reminder(Base):
    __tablename__ = "reminder"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)   # 权限隔离：只能看自己的提醒
    reminder_type = Column(String(200), nullable=False)     # 提醒内容（保持 plan.md 请求体字段名）
    reminder_time = Column(String(32), default="")          # "HH:MM"（今天）或 "YYYY-MM-DD HH:MM"（明天及以后）
    is_done = Column(Integer, default=0)                    # 0=待提醒 1=已确认（对应 /done /undo 接口）
