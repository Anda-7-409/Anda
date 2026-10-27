from AI import memory, orchestrator
from sqlalchemy.orm import Session

from Backend.models.memo import Memo
from Backend.models.user import User
from Backend.service import memo_service, reminder_service, schedule_service, upload_service
from tool import web_search   
from tool import doc_parse    
from tool import image_understand  

orchestrator.TOOLS["schedule_query"] = {
    "keywords": ("课表", "上课", "有课", "没课", "什么课", "哪些课", "几节课", "几点上课", "几点下课",
                 "上什么", "课程安排", "日程", "这周课", "全周课", "几号上课", "今天有", "明天有"),
    "exclude": ("添加", "加课", "加节", "加门", "加进", "加到", "课表加", "往课表", "记到课表", "记进课表",
                "进课表", "到课表", "新增", "新建", "录入", "排课", "录课", "删除", "移除", "提醒", "备忘"),
    "fn": schedule_service.query_tool,
}

orchestrator.TOOLS["schedule_add"] = {
    "keywords": ("添加课程", "加课", "加一节", "加一堂", "加一门", "加个课", "加节课", "加门课", "这节课加",
                 "新增课程", "新建课程", "录入", "加进课表", "加到课表", "加入课表", "排课", "录课",
                 "记到课表", "记进课表", "课表加", "往课表", "安排课", "安排一节",
                 "有一堂数", "有一节", "有门课", "有堂课"),
    "exclude": ("几点", "什么时", "多少节", "删除", "移除", "取消"),   
    "fn": schedule_service.add_tool,
}

orchestrator.TOOLS["memo_list"] = {
    "keywords": ("备忘录", "备忘", "笔记", "便签", "记了什么", "记了啥", "我记的", "记过什么", "记的东西"),
    "exclude": ("添加", "新增", "加个", "加条", "加上", "删除", "删掉", "提醒"),
    "fn": memo_service.list_tool,
}

orchestrator.TOOLS["reminder_set"] = {
    "keywords": ("提醒我", "提醒", "设置提醒", "设个提醒", "定个提醒", "加个提醒", "要提醒", "提醒一下", "记个提醒",
                 "叫我", "喊我", "催我", "提醒自己", "闹钟", "叫醒", "记住", "别忘", "记着", "到点", "留心"),
    "exclude": ("有什么", "有哪些", "哪些", "查提醒", "我的提醒", "提醒列表", "提醒过", "多少提醒", "看提醒",
                "删除", "取消", "完成", "确认"),
    "fn": reminder_service.set_tool,
}

orchestrator.TOOLS["reminder_query"] = {
    "keywords": ("有什么提醒", "有哪些提醒", "查提醒", "我的提醒", "提醒列表", "提醒过什么", "多少提醒",
                 "该提醒", "提醒事项", "待办提醒", "提醒我什么", "看提醒", "提醒过我", "提醒记录", "提醒了吗"),
    "exclude": ("添加", "设置", "设个", "定个", "加个", "叫我", "喊我", "催我", "闹钟", "新建", "录入"),
    "fn": reminder_service.query_tool,
}

orchestrator.TOOLS["doc_parse"] = {
    "keywords": ("解析", "读一下", "读这个", "读这篇", "总结这个", "总结一下这个", "写了什么", "写的什么",
                 "写的内容", "写了啥", "里面写了", "讲了什么", "讲的什么", "讲的是", "说的什么", "说的啥",
                 "内容是什么", "啥内容", "什么内容", "提取内容", "全文", "文件里", "文件内容", "这个文件",
                 "这份文件", "读文件", "帮我读",
                 "PDF", "pdf", "Word", "word", "PPT", "ppt", "论文", "文档", "课件"),
    "exclude": ("搜索", "搜一下", "帮我搜", "查一下", "查查", "官网", "网址", "新闻", "热点",
                "课表", "提醒", "备忘", "上传", "删除", "图片", "截图", "照片"),
    "fn": doc_parse.doc_parse_tool,
}

orchestrator.TOOLS["image_understand"] = {
    "keywords": ("图片里有什么", "图里", "图中", "看看这张图", "看一下这个图", "识别图片", "这是啥图",
                 "这是什么图", "截图", "图片", "照片", "画的是"),
    "exclude": ("搜索", "搜一下", "帮我搜", "上传", "删除", "课表", "提醒", "备忘", "生成", "画一张"),
    "fn": image_understand.image_understand_tool,
}

orchestrator.TOOLS["web_search"] = {
    "keywords": ("搜索", "搜一下", "搜下", "帮我搜", "全网", "网上查", "上网查", "查一下", "查查",
                 "新闻", "热点", "百科", "官网", "网址", "最新消息"),
    "exclude": ("课表", "提醒", "备忘", "笔记", "我的", "几节课", "有课", "没课"),
    "fn": web_search.search_tool,
}

TEXT_EXT = {"txt", "md", "csv", "json", "log"}
REF_MAX_CHARS = 4000   


def _build_ref_block(user: User, refs) -> str:
    parts = []
    for name in list(refs or [])[:5]:  
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
            parts.append(f"（用户引用了文件 {name}，类型 .{ext}，非文本文件内容未注入；若用户在问图片相关内容，请基于图片理解工具的真实结果回答）")
    return "\n\n".join(parts)


def chat(db: Session, user: User, utterance: str, context=None, refs=None) -> dict:
    if not utterance or not utterance.strip():
        return {"ok": False, "message": "内容不能为空哦~ 再输入一次吧 -?v?-"}
    ref_block = _build_ref_block(user, refs)
    ctx = list(context) if context else memory.recall(user.id)
    result = orchestrator.run(user.id, utterance.strip(), ctx, ref_block=ref_block)
    memory.remember(user.id, utterance.strip(), result["answer"])  
    return {"ok": True, "data": result}
