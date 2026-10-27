import threading
import time

from AI import model_router
from tool import web_search

INTERVAL_SECONDS = 60  
_started = False

def _loop() -> None:
    while True:
        time.sleep(INTERVAL_SECONDS)
        try:
            model_router.probe_down()
        except Exception as exc:
            print(f"[health] 模型探测异常: {exc}")
        try:
            web_search.probe_down()
        except Exception as exc:
            print(f"[health] 搜索源探测异常: {exc}")

def start() -> None:
    global _started
    if _started:
        return
    _started = True 
    threading.Thread(target=_loop, daemon=True).start()
    print("[health] 模型+搜索源滚动体检已启动（每60秒重测不可用项，恢复即上线）")
    model_router.probe_down() 
    web_search.probe_down()
