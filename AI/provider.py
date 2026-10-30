import os
from typing import Optional

import httpx

def call(entry: dict,payload: dict):
    body = dict(payload)
    body['model'] = entry['model_name']
    try:
        resp = httpx.post(
            entry['endpoint'],
            json=body,
            headers=_build_headers(entry),
            timeout=(10, entry['timeout']),
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as error:
        print("哎呀，这里出错了呢 -> ",error)
        return None

def extract_message(data: Optional[dict]) -> Optional[dict]:
    if not data:
        return None
    try:
        return data["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        print("哎呀，这里出错了呢 -> ",data)
        print("哎呀，这里出错了呢 -> ",data["choices"])
        print("哎呀，这里出错了呢 -> ",data["choices"][0])
        return None

def extract_text(data: Optional[dict]) -> Optional[str]:
    msg = extract_message(data)
    if msg is None:
        return None
    content = msg.get("content")
    return content if isinstance(content, str) and content else None

def _build_headers(entry: dict) -> dict:
    headers = {"Content-Type": "application/json"}
    env_name = entry.get("api_key_env") or ""
    api_key = os.environ.get(env_name, "") if env_name else ""
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers