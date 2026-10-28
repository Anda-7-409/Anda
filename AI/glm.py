from typing import List, Optional

import requests
# 从配置文件中导入必要信息
from Backend.config import GLM_API_KEY, GLM_MODEL, GLM_TIMEOUT_SECONDS, GLM_URL

def chat(messages: List[dict], model: Optional[str] = None) -> Optional[str]:
    if not GLM_API_KEY:
        return None  
    try:
        # 直接参照glm官方文档的调用方式
        resp = requests.post(  
            GLM_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {GLM_API_KEY}"},
            json={"model": model or GLM_MODEL, "messages": messages, "temperature": 0.7},
            timeout=GLM_TIMEOUT_SECONDS,
        )
        data = resp.json()
        if "choices" not in data:
            print(f"[glm] 接口异常! o-o !!! (HTTP {resp.status_code}): {data}")
            return None
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[glm] 调用失败了哦~  ?-? : {exc}")
        return None


def chat_with_tools(messages: List[dict], tools: List[dict], model: Optional[str] = None) -> Optional[dict]:
    """ 带工具表的调用。返回完整的 message dict,失败则返回 None """
    if not GLM_API_KEY:
        return None
    try:
        resp = requests.post(
            GLM_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {GLM_API_KEY}"},
            json={"model": model or GLM_MODEL, "messages": messages, "temperature": 0.7, "tools": tools},
            timeout=GLM_TIMEOUT_SECONDS,
        )
        data = resp.json()
        if "choices" not in data:
            print(f"[glm] tools 接口异常 o-o !!! (HTTP {resp.status_code}): {data}")
            return None
            # 没有返回工具问题解决，应是[“message“]而不是[“content“]
        return data["choices"][0]["message"]
    except Exception as exc:
        print(f"[glm] tools 调用失败了哦~  ?-? : {exc}")
        return None
