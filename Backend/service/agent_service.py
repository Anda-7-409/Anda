import json

from AI import orchestrator, prompts
from sqlalchemy.orm import Session

from Backend.models.memo import Memo
from Backend.models.user import User
from Backend.service import chat_history_service, memo_service, nav_service, reminder_service, schedule_service, upload_service
from Backend.service import ics_service
from tool import web_search   
from tool import doc_parse    
from tool import image_understand  
from tool import code_gen
from tool import image_gen
from tool import knowledge
from tool import translation

orchestrator.TOOLS["schedule_query"] = {
    "desc": "查询用户已录入的课表/日程。用户想知道有什么课、几点上课、某天的课程安排时使用；不用于添加、删除课程，也不用于设置提醒。",
    "keywords": ("课表", "上课", "有课", "没课", "什么课", "哪些课", "几节课", "几点上课", "几点下课",
                 "上什么", "课程安排", "日程", "这周课", "全周课", "几号上课", "今天有", "明天有"),
    "exclude": ("添加", "加课", "加节", "加门", "加进", "加到", "课表加", "往课表", "记到课表", "记进课表",
                "进课表", "到课表", "新增", "新建", "录入", "排课", "录课", "删除", "移除", "提醒", "备忘"),
    "fn": schedule_service.query_tool,
}

orchestrator.TOOLS["schedule_add"] = {
    "desc": "向用户课表添加一门新课程。用户明确要求添加/录入/排课到课表时使用；查询课表不要用这个。",
    "keywords": ("添加课程", "加课", "加一节", "加一堂", "加一门", "加个课", "加节课", "加门课", "这节课加",
                 "新增课程", "新建课程", "录入", "加进课表", "加到课表", "加入课表", "排课", "录课",
                 "记到课表", "记进课表", "课表加", "往课表", "安排课", "安排一节",
                 "有一堂数", "有一节", "有门课", "有堂课"),
    "exclude": ("几点", "什么时", "多少节", "删除", "移除", "取消"),
    "fn": schedule_service.add_tool,
}

orchestrator.TOOLS["memo_list"] = {
    "desc": "查看用户已保存的备忘录/笔记列表。用户想看自己记过什么时使用；不用于创建或删除备忘。",
    "keywords": ("备忘录", "备忘", "笔记", "便签", "记了什么", "记了啥", "我记的", "记过什么", "记的东西"),
    "exclude": ("添加", "新增", "加个", "加条", "加上", "删除", "删掉", "提醒"),
    "fn": memo_service.list_tool,
}

orchestrator.TOOLS["reminder_set"] = {
    "desc": "设置一个到点提醒（会写入数据库并在到点时通知用户）。用户要求'提醒我/叫我/别忘'某件事时使用，任务描述中必须包含具体时间和内容。",
    "keywords": ("提醒我", "提醒", "设置提醒", "设个提醒", "定个提醒", "加个提醒", "要提醒", "提醒一下", "记个提醒",
                 "叫我", "喊我", "催我", "提醒自己", "闹钟", "叫醒", "记住", "别忘", "记着", "到点", "留心"),
    "exclude": ("有什么", "有哪些", "哪些", "查提醒", "我的提醒", "提醒列表", "提醒过", "多少提醒", "看提醒",
                "删除", "取消", "完成", "确认"),
    "fn": reminder_service.set_tool,
}

orchestrator.TOOLS["reminder_query"] = {
    "desc": "查询用户已设置的提醒列表。用户想看自己有哪些提醒/待办时使用；设置新提醒不要用这个。",
    "keywords": ("有什么提醒", "有哪些提醒", "查提醒", "我的提醒", "提醒列表", "提醒过什么", "多少提醒",
                 "该提醒", "提醒事项", "待办提醒", "提醒我什么", "看提醒", "提醒过我", "提醒记录", "提醒了吗"),
    "exclude": ("添加", "设置", "设个", "定个", "加个", "叫我", "喊我", "催我", "闹钟", "新建", "录入"),
    "fn": reminder_service.query_tool,
}

orchestrator.TOOLS["calendar_export"] = {
    "desc": "把课表/提醒导出到手机或电脑的系统日历：返回课程表订阅链接（webcal，订阅一次后每周课程自动同步）"
            "和提醒 ICS 日历文件下载链接。用户说'加到日历/订阅课表/导出日历/日历文件/ics/同步到日历'时使用。",
    "keywords": ("日历", "订阅", "ics", "ICS", "导出课表", "导出提醒", "加到日历", "加入日历",
                 "同步到日历", "日历文件", "订阅课表", "订阅提醒", "日历提醒"),
    "exclude": ("删除", "移除", "取消", "退订"),
    "fn": ics_service.calendar_export_tool,
}

orchestrator.TOOLS["doc_parse"] = {
    "desc": "解析用户已上传的文档（PDF/Word/PPT/TXT/CSV）或网页链接，提取正文内容。当用户在问某个上传文件/文档链接里写了什么时使用；需要文件已在本次对话中引用或上传。",
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
    "desc": "识别用户已上传的图片内容（视觉理解）。当用户在问某张上传图片/截图里是什么时使用；需要图片已在本次对话中引用。",
    "keywords": ("图片里有什么", "图里", "图中", "看看这张图", "看一下这个图", "识别图片", "这是啥图",
                 "这是什么图", "截图", "图片", "照片", "画的是"),
    "exclude": ("搜索", "搜一下", "帮我搜", "上传", "删除", "课表", "提醒", "备忘", "生成", "画一张"),
    "fn": image_understand.image_understand_tool,
}

orchestrator.TOOLS["web_search"] = {
    "desc": "联网搜索实时信息（新闻、热点、百科、官网、天气等）。当问题需要最新/外部信息而模型自己答不了时使用；校园个人数据（课表、提醒、备忘）不要用这个。",
    "keywords": ("搜索", "搜一下", "搜下", "帮我搜", "全网", "网上查", "上网查", "查一下", "查查",
                 "新闻", "热点", "百科", "官网", "网址", "最新消息"),
    "exclude": ("课表", "提醒", "备忘", "笔记", "我的", "几节课", "有课", "没课",
                "导航", "路线", "怎么去", "怎么走"),
    "fn": web_search.search_tool,
}

orchestrator.TOOLS["code_gen"] = {
    "desc": "生成一段完整代码并保存为文件提供下载链接。用户想要'写个代码/脚本/程序/函数'并拿到文件时使用；仅解释或修改对话中的已有代码不要用这个。",
    "keywords": ("写个代码", "写一段代码", "写段代码", "写代码", "帮我写代码", "生成代码",
                 "写个脚本", "写一个脚本", "帮我写个脚本", "帮我写脚本",
                 "写个程序", "写一个程序", "帮我写个程序",
                 "写个函数", "写一个函数", "写个类", "写一个类",
                 "生成一个文件", "给我生成个文件", "帮我生成代码",
                 "帮我生成一个", "给我生成一个", "生成一个Python", "生成一个python",
                 "一段Python", "一段python", "写一个Python", "写一个python",
                 "Python代码", "python代码", "Python程序", "python程序",
                 "Python脚本", "python脚本", "代码程序", "来一段代码", "给一段代码",
                 "写个main", "写一个main"),
    "exclude": ("解释", "讲讲", "讲解", "这段", "哪里错", "报错", "运行", "执行",
                "课表", "提醒", "备忘", "笔记", "图片", "照片", "验证码", "二维码"),
    "fn": code_gen.code_gen_tool,
}

orchestrator.TOOLS["nav"] = {
    "desc": "校园导航与路线规划。用户想知道怎么去某地、导航到某地、两地怎么走时使用；返回距离、预计耗时、路线要点和高德导航链接。不用于搜索信息。",
    "keywords": ("怎么去", "怎么走", "怎么过去", "过去怎么", "导航", "路线", "带我去",
                 "如何去", "咋去", "咋走", "规划路线", "多远", "几公里"),
    "exclude": ("课表", "提醒", "备忘", "笔记", "搜索", "搜一下", "解析", "图片", "删除", "取消"),
    "fn": nav_service.nav_tool,
}

orchestrator.TOOLS["image_gen"] = {
    "desc": "根据文字描述生成一张图片（AI绘画）。用户要求画/生成/绘制图片、海报、logo、插画、头像时使用；不用于识别用户已上传的图片。",
    "keywords": ("画一张", "画个", "画一", "画幅", "帮我画", "来一张图", "生成图片", "生成一张",
                 "绘制", "画图", "画个图", "海报", "插画", "头像", "logo", "LOGO"),
    "exclude": ("识别", "看看", "看一下", "图里", "图片里", "图中", "什么图", "这是什么图",
                "删除", "上传", "解析", "描述"),
    "fn": image_gen.image_gen_tool,
}

orchestrator.TOOLS["knowledge"] = {
    "desc": "查询安工大（安徽工业大学）校园知识库：食堂美食、宿舍、奖学金、军训、报到、校园跑、体测、晚自习、保研、转专业、快递、图书馆、校区、水电网络等校园生活/制度/设施问题。用户问'学校怎么样/有什么/在哪/怎么办'这类校园问题时使用；不用于课表增删查、提醒备忘、联网搜实时新闻。",
    "keywords": ("食堂", "好吃", "吃什么", "宿舍", "寝室", "奖学金", "助学金", "军训",
                 "报到", "开学要", "开学准备", "保研", "转专业", "校园跑", "体测",
                 "晚自习", "校医院", "快递", "校园卡", "热水", "断电", "断网",
                 "空调", "图书馆", "佳山", "秀山", "校区", "四六级", "理发",
                 "安工大", "安徽工业大学", "学费", "缴费", "证件照", "校园网"),
    "exclude": ("我的课表", "加课", "添加课程", "提醒", "备忘", "搜一下", "帮我搜",
                "新闻", "热点", "画一张", "识别", "写代码", "解析", "导航", "怎么去",
                "路线", "删除", "取消"),
    "fn": knowledge.knowledge_tool,
}

orchestrator.TOOLS["translation"] = {
    "desc": "文本翻译：把一段话在中文/英文/日文/韩文/法文等语言间互译。用户明确要求'翻译'某段文字、问'用英语怎么说'时使用；不用于搜索、解析文档、生成代码。",
    "keywords": ("翻译", "译成", "译为", "译一下", "帮我译", "怎么用英语说", "怎么用英文说",
                 "用英语说", "用英文说", "中译英", "英译中"),
    "exclude": ("搜索", "搜一下", "新闻", "热点", "画一张", "识别", "写代码", "解析",
                "课表", "提醒", "备忘", "导航", "食堂", "宿舍"),
    "fn": translation.translation_tool,
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
            parts.append(prompts.P("agent_service.ref_non_text", name=name, ext=ext))
    return "\n\n".join(parts)


def chat(db: Session, user: User, utterance: str, context=None, refs=None, chat_id=None) -> dict:
    if not utterance or not utterance.strip():
        return {"ok": False, "message": "内容不能为空哦 (。•́︿•̀。) 想聊点什么呀？"}
    ref_block = _build_ref_block(user, refs)
    ctx = list(context) if context else chat_history_service.recall_window(db, user.id)
    result = orchestrator.run(user.id, utterance.strip(), ctx, ref_block=ref_block, refs=list(refs or []))
    if chat_id:
        # 带上 chat_id 才落库；页面记录与模型记忆同源（app.db/chat_message）
        chat_history_service.save_message(db, user.id, chat_id, "user", utterance.strip())
        chat_history_service.save_message(db, user.id, chat_id, "ai", result["answer"])
    return {"ok": True, "data": result}

def chat_stream(db: Session, user: User, utterance: str, refs=None, chat_id=None):
    # 流式对话：与 chat() 同一套 ref_block/记忆逻辑；消息实时落库 app.db/chat_message
    ref_block = _build_ref_block(user, refs)
    ctx = chat_history_service.recall_window(db, user.id)   # 先取旧上下文再存本轮提问，模型不会重复看到当前问题
    if chat_id:
        chat_history_service.save_message(db, user.id, chat_id, "user", utterance.strip())
    answer, reasoning = "", ""
    try:
        for ev in orchestrator.run_stream(user.id, utterance.strip(), ctx,
                                          ref_block=ref_block, refs=list(refs or [])):
            yield ev
            if ev["type"] == "tools":
                for t in ev.get("tool_calls") or []:
                    chat_history_service.save_message(
                        db, user.id, chat_id, "tool",
                        json.dumps(t.get("result"), ensure_ascii=False), tool=t.get("tool_name", ""))
            elif ev["type"] == "content":
                answer += ev["delta"]
            elif ev["type"] == "reasoning":
                reasoning += ev["delta"]
    finally:
        # finally 保证客户端中途断开时已生成的部分也落库（GeneratorExit 同样走 finally）
        if chat_id and (answer or reasoning):
            chat_history_service.save_message(db, user.id, chat_id, "ai", answer, reasoning=reasoning)