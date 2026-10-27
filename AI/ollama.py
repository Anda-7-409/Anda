from typing import List, Optional

import requests

from Backend.config import OLLAMA_MODEL, OLLAMA_TIMEOUT_SECONDS, OLLAMA_URL

def chat(messages: List[dict], model: Optional[str] = None) -> Optional[str]:
    try:
        resp = requests.post(
            f"{OLLAMA_URL.rstrip('/')}/api/chat",
            json={"model": model or OLLAMA_MODEL, "messages": messages, "stream": False},
            timeout=OLLAMA_TIMEOUT_SECONDS,
        )
        data = resp.json()
        return data.get("message", {}).get("content")
    except Exception as exc:
        print(f"[ollama] 调用失败了哦~(没准是本地服务还没启动?) ?-?: {exc}")
        return None
