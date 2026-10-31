from contextlib import asynccontextmanager
from .database import init_db, close_db

from fastapi import FastAPI
from dotenv import load_dotenv
load_dotenv()

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
                         "search": web_search.status()}}
    return app

def register_routes(app: FastAPI):
    from .routes import auth, agent, schedule, upload, memo, reminder, nav
    app.include_router(auth.router, prefix="/auth")
    app.include_router(agent.router, prefix="/agent")
    app.include_router(schedule.router, prefix="/schedule")
    app.include_router(upload.router, prefix="/upload")
    app.include_router(memo.router, prefix="/memo")
    app.include_router(reminder.router, prefix="/reminder")
    app.include_router(nav.router, prefix="/nav")


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("Backend.app:app", host="127.0.0.1", port=8000, reload=True)
    
