# (智能体业务逻辑) 承上启下：取上下文记忆 → 读引用文件 → 跑orchestrator流水线 → 记住本轮
from AI import memory, orchestrator
from sqlalchemy.orm import Session

from Backend.models.memo import Memo
from Backend.models.user import User
from Backend.service import memo_service, schedule_service, upload_service

# 注册 Agent 工具（skill/ 模块落地后在此批量注册）
# orchestrator._plan_tools 按 keywords 拆解任务，再以 fn(utterance=, user_id=) 调用
# 关键词互补：“课程”归添加，查询靠 课表/有课/什么课 等，避免“添加课程”同时命中只读查询
orchestrator.TOOLS["schedule_query"] = {
    "keywords": ("课表", "上课", "有课", "没课", "什么课", "哪些课"),
    "fn": schedule_service.query_tool,
}
# 自然语言加课：模型抽取→校验→写库；成功后由模型在答案里回显字段供用户核对
orchestrator.TOOLS["schedule_add"] = {
    "keywords": ("添加课程", "加课", "加一节", "加一门", "加个课", "加节课", "这节课加",
                 "新增课程", "新建课程", "录入", "加进课表", "加到课表", "加入课表", "排课", "录课"),
    "fn": schedule_service.add_tool,
    }
# 添加 memo_list 工具，让 Agent 能读出今日日程的备忘录（关键词避开"什么/有"类泛词，防与课表查询同时命中混答）
orchestrator.TOOLS["memo_list"] = {
    "keywords": ("备忘录", "备忘", "笔记", "记了什么", "记了啥"),
    "fn": memo_service.list_tool,
}

# 能直接读出文字注入对话的扩展名；其余（图片/Office等）只告诉模型文件名，待视觉模型接入后升级
TEXT_EXT = {"txt", "md", "csv", "json", "log"}
REF_MAX_CHARS = 4000   # 单个引用文件注入的字符上限，防撑爆上下文


def _build_ref_block(user: User, refs) -> str:
    # 把 @文件名 解析成可注入的文本块；文件不存在/不属于当前用户则跳过（upload_service 已做权限隔离）
    parts = []
    for name in list(refs or [])[:5]:  # 一次最多引用 5 个
        got = upload_service.get_file_path(user.id, str(name))
        if not got["ok"]:
            parts.append(f"（引用失败：{name}，{got['message']}）")
            continue
        path = got["data"]["path"]
        ext = path.suffix.lower().lstrip(".")
        if ext in TEXT_EXT:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")[:REF_MAX_CHARS]
                parts.append(f"【引用文件 {name}】\n{text}")
            except Exception:
                parts.append(f"（引用文件 {name} 读取失败）")
        else:
            parts.append(f"（用户引用了文件 {name}，类型 .{ext}；当前仅能读取文本类文件，可在回答中提醒用户）")
    return "\n\n".join(parts)


def chat(db: Session, user: User, utterance: str, context=None, refs=None) -> dict:
    if not utterance or not utterance.strip():
        return {"ok": False, "message": "内容不能为空哦~ 再输入一次吧 -?v?-"}
    text = utterance.strip()
    ref_block = _build_ref_block(user, refs)
    if ref_block:
        text = f"{text}\n\n{ref_block}"   # 引用内容拼进本轮用户消息，模型直接“看到”文件
    ctx = list(context) if context else memory.recall(user.id)
    result = orchestrator.run(user.id, text, ctx)
    memory.remember(user.id, utterance.strip(), result["answer"])  # 记忆存原文，不把文件内容堆进历史
    # TODO：任务记录写入 task 表（task模块落地后），供 /task 列表与 task_detail.html 跳转
    return {"ok": True, "data": result}