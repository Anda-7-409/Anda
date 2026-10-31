# prompts.py — 提示词集中管理加载器：prompt.json 是唯一来源，P() 点路径取用 + {变量} 插值
# 设计：启动时加载一次进内存；文件/键/变量缺失只告警并返回可见占位符，绝不炸服务
import json
import logging
from pathlib import Path

log = logging.getLogger("anda.prompts")

_FILE = Path(__file__).with_name("prompt.json")
_data: dict = {}

try:
    loaded = json.loads(_FILE.read_text(encoding="utf-8"))
    if isinstance(loaded, dict):
        _data = loaded
    else:
        log.warning("prompt.json 顶层不是对象，提示词全部走占位符 (。•́︿•̀。)")
except FileNotFoundError:
    log.warning("找不到 %s，提示词全部走占位符 (。•́︿•̀。)", _FILE)
except Exception as e:
    log.warning("prompt.json 解析失败（%s），提示词全部走占位符 (＞﹏＜)", e)


def P(path: str, **kw) -> str:
    """取提示词并插值：P("translation.user", target="英文", q="hello")
    路径/键缺失 → 返回 [缺少提示词 xxx]；插值变量缺失 → 按原样返回并告警。"""
    node = _data
    for k in path.split("."):
        if isinstance(node, dict) and k in node:
            node = node[k]
        else:
            log.warning("提示词缺失：%s (´･ω･`)", path)
            return f"[缺少提示词 {path}]"
    if not isinstance(node, str):
        log.warning("提示词 %s 不是字符串，按原样返回 (。•́︿•̀。)", path)
        return str(node)
    try:
        return node.format(**kw)
    except (KeyError, IndexError) as e:
        log.warning("提示词 %s 插值缺变量 %s，按原样返回 (。•́︿•̀。)", path, e)
        return node
