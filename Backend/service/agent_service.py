# (智能体业务逻辑) 承上启下：取上下文记忆 → 读引用文件 → 跑orchestrator流水线 → 记住本轮
from AI import memory, orchestrator
from sqlalchemy.orm import Session

from Backend.models.memo import Memo
from Backend.models.user import User
from Backend.service import memo_service, reminder_service, schedule_service, upload_service

# 注册 Agent 工具（skill/ 模块落地后在此批量注册）
# orchestrator._plan_tools 按 keywords 拆解任务、exclude 排除冲突，再以 fn(utterance=, user_id=) 调用
# 关键词放宽策略：覆盖口语变体；防冲突靠 exclude——含排除词则该工具不触发（如“有什么提醒”不走设提醒）
orchestrator.TOOLS["schedule_query"] = {
    "keywords": ("课表", "上课", "有课", "没课", "什么课", "哪些课", "几节课", "几点上课", "几点下课",
                 "上什么", "课程安排", "日程", "这周课", "全周课", "几号上课", "今天有", "明天有"),
    "exclude": ("添加", "加课", "加节", "加门", "加进", "加到", "课表加", "往课表", "记到课表", "记进课表",
                "进课表", "到课表", "新增", "新建", "录入", "排课", "录课", "删除", "移除", "提醒", "备忘"),
    "fn": schedule_service.query_tool,
}
# 自然语言加课：模型抽取→校验→写库；成功后由模型在答案里回显字段供用户核对
orchestrator.TOOLS["schedule_add"] = {
    "keywords": ("添加课程", "加课", "加一节", "加一堂", "加一门", "加个课", "加节课", "加门课", "这节课加",
                 "新增课程", "新建课程", "录入", "加进课表", "加到课表", "加入课表", "排课", "录课",
                 "记到课表", "记进课表", "课表加", "往课表", "安排课", "安排一节",
                 "有一堂数", "有一节", "有门课", "有堂课"),
    "exclude": ("几点", "什么时", "多少节", "删除", "移除", "取消"),   # “下一节课几点”是查不是加
    "fn": schedule_service.add_tool,
}
# 备忘录读取：避开写入/提醒类词，防与 reminder_set、schedule 双向混答
orchestrator.TOOLS["memo_list"] = {
    "keywords": ("备忘录", "备忘", "笔记", "便签", "记了什么", "记了啥", "我记的", "记过什么", "记的东西"),
    "exclude": ("添加", "新增", "加个", "加条", "加上", "删除", "删掉", "提醒"),
    "fn": memo_service.list_tool,
}
# 自然语言设置提醒：模型抽取→校验→写库（与 schedule_add 同款），成功后由模型回显内容与时间供核对
orchestrator.TOOLS["reminder_set"] = {
    "keywords": ("提醒我", "提醒", "设置提醒", "设个提醒", "定个提醒", "加个提醒", "要提醒", "提醒一下", "记个提醒",
                 "叫我", "喊我", "催我", "提醒自己", "闹钟", "叫醒", "记住", "别忘", "记着", "到点", "留心"),
    "exclude": ("有什么", "有哪些", "哪些", "查提醒", "我的提醒", "提醒列表", "提醒过", "多少提醒", "看提醒",
                "删除", "取消", "完成", "确认"),
    "fn": reminder_service.set_tool,
}
# 查询提醒：靠 exclude 挡住设提醒类词，与 reminder_set 保持互补
orchestrator.TOOLS["reminder_query"] = {
    "keywords": ("有什么提醒", "有哪些提醒", "查提醒", "我的提醒", "提醒列表", "提醒过什么", "多少提醒",
                 "该提醒", "提醒事项", "待办提醒", "提醒我什么", "看提醒", "提醒过我", "提醒记录", "提醒了吗"),
    "exclude": ("添加", "设置", "设个", "定个", "加个", "叫我", "喊我", "催我", "闹钟", "新建", "录入"),
    "fn": reminder_service.query_tool,
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