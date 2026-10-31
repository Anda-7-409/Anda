# chat_history_service.py — 聊天记录服务（app.db/chat_message 单一真相源）
# 页面记录（跨设备同步）与模型记忆（最近12条窗口）都从这张表派生，
# 替代原 AI/memory.py 的 chat_history 滑窗 + chat_sync 整包双写
from sqlalchemy.orm import Session

from Backend.models.chat import ChatMessage


def _msg_dict(m: ChatMessage) -> dict:
    d = {"role": m.role, "content": m.content or ""}
    if m.tool:
        d["tool"] = m.tool
    if m.reasoning:
        d["reasoning"] = m.reasoning
    return d


def save_message(db: Session, user_id: int, chat_id: str, role: str,
                 content: str, tool: str = "", reasoning: str = "") -> None:
    if not chat_id or content is None:
        return
    db.add(ChatMessage(user_id=user_id, chat_id=str(chat_id)[:32], role=role,
                       content=str(content), tool=tool or "", reasoning=reasoning or ""))
    db.commit()


def delete_chat(db: Session, user_id: int, chat_id: str) -> int:
    n = db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id, ChatMessage.chat_id == str(chat_id)).delete()
    db.commit()
    return n


def build_history(db: Session, user_id: int) -> list:
    # 重建前端 history 数组结构：[{id, title, time, messages:[...]}]，最新对话在前
    # 标题取该对话第一条 user 消息前15字（与前端命名规则一致），时间为首条消息时刻
    rows = db.query(ChatMessage).filter(ChatMessage.user_id == user_id)\
             .order_by(ChatMessage.id).all()
    chats = {}
    for m in rows:
        c = chats.setdefault(m.chat_id, {"id": m.chat_id, "title": "新对话", "time": "",
                                         "messages": [], "_last_id": m.id})
        c["messages"].append(_msg_dict(m))
        c["_last_id"] = m.id
        if m.role == "user" and c["title"] == "新对话":
            c["title"] = (m.content or "").strip()[:15] or "新对话"
        if not c["time"] and m.created_at:
            c["time"] = m.created_at.strftime("%Y-%m-%d %H:%M")
    items = list(chats.values())
    items.sort(key=lambda c: c["_last_id"], reverse=True)
    for c in items:
        c.pop("_last_id")
    return items


def recall_window(db: Session, user_id: int, limit: int = 12) -> list:
    # 模型记忆：最近 limit 条 user/ai 消息（工具消息不进模型上下文，与旧 memory.py 行为一致）
    rows = db.query(ChatMessage).filter(
        ChatMessage.user_id == user_id,
        ChatMessage.role.in_(("user", "ai")))\
        .order_by(ChatMessage.id.desc()).limit(limit).all()
    return [{"role": r.role, "content": r.content} for r in reversed(rows)]
