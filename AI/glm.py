from typing import List, Optional

import requests
import json

from Backend.config import GLM_API_KEY, GLM_MODEL, GLM_TIMEOUT_SECONDS, GLM_URL
# 调用glm模型
def chat(messages: List[dict]) -> Optional[str]:
    if not GLM_API_KEY:
        return None  # 未配置Key → 跳过，由路由尝试另一个模型
    try:
        resp = requests.post(
            GLM_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {GLM_API_KEY}"},
            json={"model": GLM_MODEL, "messages": messages, "temperature": 0.7},
            timeout=GLM_TIMEOUT_SECONDS,
        )
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[glm] 调用失败了哦~  ?-? : {exc}")
        return None