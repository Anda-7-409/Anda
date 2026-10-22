# prompt.py (提示词生成) 构造发给模型的消息：系统人设 + 上下文记忆 + 用户问题
# TODO：知识库（knowledge.db）落地后，在此拼入办事"动作级"信息（去哪办、带什么、先办什么）
from typing import List, Optional

SYSTEM_PROMPT = """你是"安答"，安徽工业大学的校园AI Agent助手。
你的职责：
1. 课表、作业、考试、复习计划等学习安排类问题（后续可驱动课表导入、提醒设置等工具完成）
2. 校园办事流程咨询（去哪办、带什么材料、先办什么）
3. 通用校园生活问答
回答要求：简体中文、简洁条目化；不编造制度条文，不确定的办事流程请提醒用户以学校官方通知为准。"""

CONTEXT_WINDOW = 6  # 带入模型的历史轮数上限

def build_messages(utterance: str, context: Optional[List[dict]] = None) -> List[dict]:
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if context:
        for turn in context[-CONTEXT_WINDOW:]:
            role = turn.get("role")
            content = turn.get("content")
            if content and role in ("user", "ai", "assistant"):
                # 前端历史用 ai 角色，模型API要求 assistant，做一次映射
                messages.append({"role": "assistant" if role == "ai" else role, "content": str(content)})
    messages.append({"role": "user", "content": utterance})
    return messages