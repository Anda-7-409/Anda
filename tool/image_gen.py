# image_gen.py — 文生图：Kolors(w10) → CogView-3-Flash(w6) 两级降级
# 说明：/images/generations 不是 chat 端点，走不了 model_router 能力链，故自管源顺序
import logging
import os

import requests

log = logging.getLogger("anda.image_gen")
_TIMEOUT = 120

def _kolors(prompt: str) -> str:
    key = os.environ.get("SILICONFLOW_API_KEY", "")
    if not key:
        raise RuntimeError("未配置 SILICONFLOW_API_KEY")
    r = requests.post("https://api.siliconflow.cn/v1/images/generations",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": "Kwai-Kolors/Kolors", "prompt": prompt},
                      timeout=_TIMEOUT)
    r.raise_for_status()
    d = r.json()
    url = ((d.get("images") or d.get("data") or [{}])[0]).get("url")
    if not url:
        raise RuntimeError("Kolors 未返回图片")
    return url

def _cogview(prompt: str) -> str:
    key = os.environ.get("GLM_API_KEY", "")
    if not key:
        raise RuntimeError("未配置 GLM_API_KEY")
    r = requests.post("https://open.bigmodel.cn/api/paas/v4/images/generations",
                      headers={"Authorization": f"Bearer {key}"},
                      json={"model": "CogView-3-Flash", "prompt": prompt},
                      timeout=_TIMEOUT)
    r.raise_for_status()
    url = ((r.json().get("data") or [{}])[0]).get("url")
    if not url:
        raise RuntimeError("CogView 未返回图片")
    return url

def image_gen_tool(utterance="", user_id=None, refs=None, **_) -> dict:
    prompt = (utterance or "").strip()
    if not prompt:
        return {"ok": False, "error": "没有描述要画什么"}
    for name, fn in (("kolors", _kolors), ("cogview", _cogview)):
        try:
            url = fn(prompt)
            return {"ok": True, "image_url": url, "provider": name,
                    "hint": "回答时必须原样输出 image_url 链接文本，方便用户点击查看；链接有时效性，提醒用户尽快保存"}
        except Exception as e:
            log.warning("嗷！%s 画图服务挂啦 ：-： %s", name, e)
    return {"ok": False, "error": "画图服务暂时都不可用，请稍后再试"}
