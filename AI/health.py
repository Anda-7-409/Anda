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
        log.info("安答模型低频探活开始#:#")
        # 对已配置密钥的 chat 模型发 1-token 探活请求，结果供 /health 展示
        try:
            from AI import model_router
            model_router.probe_down()
            log.info("安答模型低频探活完成#:#")
        except Exception as e:
            log.warning("安答模型低频探活失败#:#: %s", e)