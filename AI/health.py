import threading, time, logging

log = logging.getLogger("anda.health")
_started = False

def start():
    global _started
    if _started:
        return
    _started = True
    log.info("安答模型健康检查启动#:#")
    threading.Thread(target=_loop, daemon=True).start()

def _loop():
    while _started:
        time.sleep(300)
        log.info("安答模型健康检查#:#")
        # 检查模型是否健康
        try:
            from AI import model_router
            model_router.probe_down()
            log.info("安答模型健康检查通过#:#")
        except Exception as e:
            log.warning("安答模型健康检查失败#:#: %s", e)