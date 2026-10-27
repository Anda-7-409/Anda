from typing import List, Optional

import requests

from Backend.config import GLM_API_KEY, GLM_MODEL, GLM_TIMEOUT_SECONDS, GLM_URL

def chat(messages: List[dict], model: Optional[str] = None) -> Optional[str]:
    if not GLM_API_KEY:
        return None  
    try:
        resp = requests.post(  
            GLM_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {GLM_API_KEY}"},
            json={"model": model or GLM_MODEL, "messages": messages, "temperature": 0.7},
            timeout=GLM_TIMEOUT_SECONDS,
        )
        data = resp.json()
        if "choices" not in data:
            print(f"[glm] 接口异常 o-o !!! (HTTP {resp.status_code}): {data}")
            return None
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[glm] 调用失败了哦~  ?-? : {exc}")
        return None
