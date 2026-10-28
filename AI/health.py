import threading
import time

from AI import model_router
from tool import web_search
# -V- 采用了中转站大哥们（openrouter）的思路，哪个模型可以使用哪个模型
Check_time = 300
_started = False

def _loop() -> None:
    while True:
        time.sleep(Check_time)
        try:
            model_router.probe_down()
        except Exception as exc:
            print(f"[health] 模型出现异常啦！: {exc}")
        try:
            web_search.probe_down()
        except Exception as exc:
            print(f"[health] 搜索源出现异常啦！: {exc}")

def start() -> None:
    global _started
    if _started:
        return
    _started = True 
    threading.Thread(target=_loop, daemon=True).start()
    print(f"[health] 模型+搜索源滚动体检已启动嘞~（每{Check_time}秒重测不可用滴源）")
    model_router.probe_down() 
    web_search.probe_down()
