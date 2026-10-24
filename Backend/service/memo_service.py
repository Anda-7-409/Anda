
# memo_service.py (备忘录业务) 今日日程备忘的增删查；同一套业务同时供路由层与 Agent 工具复用
from typing import List

from sqlalchemy.orm import Session

from Backend.database import SessionLocal
from Backend.models.memo import Memo

def _to_dict(m: Memo) -> dict:
    # 返回契约：与前端备忘条目字段一致，前端零改动即可渲染
    return {
        "id": m.id,
        "content": m.content,
        "created_at": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
    }

def _list(db: Session, user_id: int) -> List[Memo]:
    # 所有查询强制带 user_id 条件：只能看到自己的备忘（与 schedule/upload 同思路）
    return db.query(Memo).filter(Memo.user_id == user_id).order_by(Memo.id.desc()).all()

def list_memos(db: Session, user_id: int) -> dict:
    return {"ok": True, "data": [_to_dict(m) for m in _list(db, user_id)]}

def add_memo(db: Session, user_id: int, content: str) -> dict:
    text = (content or "").strip()
    if not text:
        return {"ok": False, "message": "备忘录内容不能为空哦~"}
    if len(text) > 200:
        return {"ok": False, "message": "备忘录太长啦，200 字以内哦 ~"}
    memo = Memo(user_id=user_id, content=text)
    db.add(memo)
    db.commit()
    db.refresh(memo)
    return {"ok": True, "data": _to_dict(memo)}

def delete_memo(db: Session, user_id: int, memo_id: int) -> dict:
    memo = db.query(Memo).filter(Memo.id == memo_id, Memo.user_id == user_id).first()
    if not memo:
        return {"ok": False, "message": "备忘录不存在或不属于你哦~"}
    db.delete(memo)
    db.commit()
    return {"ok": True, "data": {"id": memo_id}}

def list_tool(utterance: str, user_id: int) -> dict:
    # Agent 工具入口：orchestrator 以 fn(utterance=, user_id=) 调用，拿不到请求级 db → 自建会话
    with SessionLocal() as db:
        memos = [_to_dict(m) for m in _list(db, user_id)]
    return {"count": len(memos), "memos": memos}
