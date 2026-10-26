# prompt.py (提示词生成) 构造发给模型的消息：设定的模型人设 + 上下文 + 用户问题
# TODO：知识库 knowledge.txt 
from typing import List, Optional

# 模型人设提示词定位：身份，职责，回答，要求，工具调用，写库类操作 注意：此部分不跟历史传递，每次对话都重新注入
MODEL_PROMPT = """你是"安答"，安徽工业大学的校园AI Agent助手。
你的职责：
1. 课表、作业、考试、复习计划等学习安排类问题（后续可驱动课表导入、提醒设置等工具完成）
2. 校园办事流程咨询（去哪办、带什么材料、先办什么）
3. 通用校园生活问答
回答要求：简体中文、简洁条目化；不编造制度条文，不确定的办事流程请提醒用户以学校官方通知为准。
写库类操作（设置提醒、添加课程等）只有当对话中【工具执行结果】明确返回 ok:true 时，才能声称"已设置/已添加"；
没有工具结果或结果为失败时，必须如实告知没做成并说明原因（如缺少时间、模型暂不可用等），严禁编造已完成。
回答时可以适度添加个性化词汇，如“呀~”“哦~”“嗯~”等，和颜文字，以增强互动性。
"""
CONTEXT_WINDOW = 6  # 带入模型的历史轮数上限

def build_messages(utterance: str, context: Optional[List[dict]] = None) -> List[dict]:
    messages = [{"role": "system", "content": MODEL_PROMPT}]
    if context:
        for turn in context[-CONTEXT_WINDOW:]:
            role = turn.get("role")
            content = turn.get("content")
            if content and role in ("user", "ai", "assistant"):
                # 前端历史用 ai 角色，模型API要求 assistant，做一次映射
#                 - 首条消息 固定为 system 角色，注入 MODEL_PROMPT
# - 裁剪历史 ：`context[-CONTEXT_WINDOW:]` 只取最后 6 条
# - 角色映射 （最容易忽略的细节）：前端存储的历史消息用`"ai"` 作为角色，但模型 API 只认`"assistant"` ，所以这里做了`"ai" → "assistant"` 的转换，同时过滤掉空内容和非法角色
# - 追加当前问题 为
                messages.append({"role": "assistant" if role == "ai" else role, "content": str(content)})
    messages.append({"role": "user", "content": utterance})
    return messages