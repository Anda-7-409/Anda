from contextlib import asynccontextmanager
from .database import init_db, close_db

from fastapi import FastAPI
# .env 加载统一由 Backend/config._load_env 负责（上面 import 链已触发），此处不再重复加载

def create_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        init_db()
        from AI import health
        health.start()
        yield
        close_db()
    app = FastAPI(title="Anda API", version="0.0.1", lifespan=lifespan)
    register_routes(app)
    @app.get("/health")
    def health():
        from AI import model_router
        from tool import web_search
        return {"code": 0, "message": "ok",
                "data": {"service": "anda-api", "models": model_router.status(),
                         "search": web_search.status(),
                         "note": "models.ok 为最近一次低频探活结果（仅 chat 能力模型每5分钟探活一次，"
                                 "其余能力为配置检查）；checked_at 为最近探活时间，未探活则为 null"}}
    return app

def register_routes(app: FastAPI):
    from .routes import auth, agent, schedule, upload, memo, reminder, nav, asr
    app.include_router(auth.router, prefix="/auth")
    app.include_router(agent.router, prefix="/agent")
    app.include_router(schedule.router, prefix="/schedule")
    app.include_router(upload.router, prefix="/upload")
    app.include_router(memo.router, prefix="/memo")
    app.include_router(reminder.router, prefix="/reminder")
    app.include_router(nav.router, prefix="/nav")
    app.include_router(asr.router, prefix="/asr")


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Backend.app:app", host="127.0.0.1", port=8000, reload=True)
    
