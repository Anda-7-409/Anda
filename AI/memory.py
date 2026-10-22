from typing import List

_history: dict = {}
MAX_TURNS = 12  # 每用户最多记住的条数

def recall(user_id: int) -> List[dict]:
    return list(_history.get(user_id, []))

def remember(user_id: int, utterance: str, answer: str) -> None:
    turns = _history.setdefault(user_id, [])
    turns.append({"role": "user", "content": utterance})
    turns.append({"role": "ai", "content": answer})
    if len(turns) > MAX_TURNS:
        del turns[: len(turns) - MAX_TURNS]