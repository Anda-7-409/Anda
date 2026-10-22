# 模型路由 用于路由用户任务到不同的模型，如glm模型、ollama模型等  如果电脑上没有 ollama或调用失败，则自动使用 glm模型
from typing import List , Optional, Tuple

from AI import glm, ollama

# 复杂任务关键词：命中即走云端GLM（课表/作业/考试等准确性优先），否则走本地Ollama
COMPLEX_KEYWORDS = (
    "课表", "作业", "考试", "复习", "提醒", "日程", "计划",
    "成绩", "GPA", "学分", "导入", "安排", "复习表", "课程",
)

def pick_provider(utterance: str) -> str:
    # 意图复杂度判断（第一版规则匹配，第二版可升级为LLM意图识别）
    if any(word in utterance for word in COMPLEX_KEYWORDS):
        return "glm"
    return "ollama"

def chat(messages: List[dict]) -> Tuple[Optional[str], Optional[str]]:
    # 返回 (回复正文, 实际使用的提供方)；两个模型都不可用时返回 (None, None)
    utterance = messages[-1]["content"] if messages else ""
    primary = pick_provider(utterance)
    fallback = "ollama" if primary == "glm" else "glm"
    for name in (primary, fallback):  # 主模型不可用自动降级尝试另一个
        text = glm.chat(messages) if name == "glm" else ollama.chat(messages)
        if text:
            return text, name
    return None, None