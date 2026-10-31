from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from Backend.database import Base

class ChatMessage(Base):
    # 聊天记录单一真相源：页面跨设备记录与模型记忆都从这张表派生
    __tablename__ = "chat_message"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=False)
    chat_id = Column(String(32), index=True, nullable=False)   # 前端生成的 'c_'+时间戳，一个对话一组
    role = Column(String(16), nullable=False)                   # user / ai / tool
    content = Column(Text, nullable=False)
    tool = Column(String(32), default="")                       # role=tool 时的工具名
    reasoning = Column(Text, default="")                        # role=ai 时的思考过程
    created_at = Column(DateTime, default=datetime.utcnow)
