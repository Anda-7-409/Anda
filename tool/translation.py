# translation.py — 文本翻译：Hunyuan-MT（translation 权重 10）滑链
# 契约（docs/refactoring.md 3.1）：fn(utterance, user_id, **_) -> dict；utterance 为 FC 生成的 task 参数
from AI import model_router, prompts

# 目标语言识别：从原话关键词猜；没指定就中英互转（含中文按语境猜）
_FOREIGN = (("日语", "日语"), ("日文", "日语"), ("韩语", "韩语"), ("韩文", "韩语"),
            ("法语", "法语"), ("德语", "德语"), ("俄语", "俄语"),
            ("英文", "英文"), ("英语", "英文"))


def _target(q: str) -> str:
    for k, t in _FOREIGN:
        if k in q:
            return t
    # 原文几乎全 ASCII → 大概率是英文，翻成中文；否则翻成英文
    ascii_ratio = sum(1 for c in q if ord(c) < 128) / max(len(q), 1)
    return "中文" if ascii_ratio > 0.7 else "英文"


def translation_tool(utterance, user_id, **_):
    q = (utterance or "").strip()
    if not q:
        return {"ok": False, "message": "没有要翻译的内容哦 ~"}
    target = _target(q)
    try:
        msg, _ = model_router.chat("translation", [
            {"role": "system", "content": prompts.P("translation.sys")},
            {"role": "user", "content": prompts.P("translation.user", target=target, q=q)},
        ])
        out = (msg.get("content") or "").strip()
    except Exception:
        return {"ok": False, "message": "翻译服务暂时不可用，稍后再试试 ~"}
    if not out:
        return {"ok": False, "message": "翻译结果为空，换个说法试试 ~"}
    return {"ok": True, "data": {"translation": out, "target": target}}
