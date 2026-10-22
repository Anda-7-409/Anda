# (智能体业务逻辑) 承上启下：取上下文记忆 → 跑orchestrator流水线 → 记住本轮
from AI import memory, orchestrator
from sqlalchemy.orm import Session

from Backend.models.user import User

def chat(db: Session, user: User, utterance: str, context=None) -> dict:
    if not utterance or not utterance.strip():
        return {"ok": False, "message": "内容不能为空哦~ 再输入一次吧 -?v?-"}
    ctx = list(context) if context else memory.recall(user.id)
    result = orchestrator.run(user.id, utterance.strip(), ctx)
    memory.remember(user.id, utterance.strip(), result["answer"])
    # TODO：任务记录写入 task 表（task模块落地后），供 /task 列表与 task_detail.html 跳转
    return {"ok": True, "data": result}