#  模型滚动体检 后台线程定期探测不可用的候选模型，恢复即自动回到可用队列
import threading
import time

from AI import model_router

INTERVAL_SECONDS = 60  # 探测间隔
_started = False

def _loop() -> None:
    while True:
        time.sleep(INTERVAL_SECONDS)
        try:
            model_router.probe_down()
        except Exception as exc:
            print(f"[health] 探测异常: {exc}")

def start() -> None:
    global _started
    if _started:
        return
    _started = True  # 防止热重载时重复起线程
    threading.Thread(target=_loop, daemon=True).start()
    print("[health] 模型滚动体检已启动（每60秒重测不可用模型，恢复即上线）")
    model_router.probe_down()  # 启动立即体检一轮