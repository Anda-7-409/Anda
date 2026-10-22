from typing import List, Optional

import requests

from Backend.config import GLM_API_KEY, GLM_MODEL, GLM_TIMEOUT_SECONDS, GLM_URL
# 调用glm模型
def chat(messages: List[dict], model: Optional[str] = None) -> Optional[str]:
    # model 参数供候选池滚动测试逐个指定模型，不传则用 config 默认槽位
    if not GLM_API_KEY:
        return None  # 未配置Key → 跳过，由路由尝试另一个模型
    try:
        resp = requests.post(
            GLM_URL,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {GLM_API_KEY}"},
            json={"model": model or GLM_MODEL, "messages": messages, "temperature": 0.7},
            timeout=GLM_TIMEOUT_SECONDS,
        )
        data = resp.json()
        if "choices" not in data:
            # 智谱报错时不抛HTTP异常而是返回error结构，这里显式拦截，否则真实原因会被KeyError吞掉
            print(f"[glm] 接口异常(HTTP {resp.status_code}): {data}")
            return None
        return data["choices"][0]["message"]["content"]
    except Exception as exc:
        print(f"[glm] 调用失败了哦~  ?-? : {exc}")
        return None