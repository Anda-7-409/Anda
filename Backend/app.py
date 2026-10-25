# app.py(主程序)  用于初始化数据库连接、处理用户请求、调用其他模块等 FastAPI/Flask 工厂函数
# 该文件是后端应用的入口，负责创建应用实例、配置数据库连接、注册路由等。
from contextlib import asynccontextmanager
from .database import init_db, close_db

from fastapi import FastAPI


def create_app() -> FastAPI:
    # lifespan：启动时初始化数据库，关闭时释放连接（引用 database.py，建好后再填）
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # 初始化数据库连接 启动钩子 
        # TODO: init_db()  建 app.db 表（等 database.py）
        init_db()
        # 模型滚动体检：后台线程定期探测不可用候选模型，恢复自动上线
        from AI import health
        health.start()
        # 关闭数据库连接 关闭钩子
        # TODO: close_db() 释放连接
        yield
        # TODO: close_db() 释放连接
        close_db()

    app = FastAPI(title="Anda API", version="0.0.1", lifespan=lifespan)

    # TODO: 配置 CORS            → add_cors(app)      等 middleware/cors.py
    # TODO: 注册异常处理         → register_exceptions(app)  等 exception/
    # TODO: 注册中间件（日志/限流）→ add_middleware(app) 等 middleware/
    # 注册路由（一个模块一个 router，接口详见 plan.md）
    register_routes(app)
    # TODO: 挂载静态文件         → mount_static(app)   生产模式挂 Frontend/

    # 自检接口：启动后访问 http://localhost:8000/health 验证服务是否正常
    @app.get("/health")
    def health():
        from AI import model_router
        from tool import web_search
        return {"code": 0, "message": "ok",
                "data": {"service": "anda-api", "models": model_router.status(),
                         "search": web_search.status()}}

    return app


def register_routes(app: FastAPI):
    from .routes import auth, agent, schedule, upload, memo, reminder
    app.include_router(auth.router, prefix="/auth")
    app.include_router(agent.router, prefix="/agent")
    app.include_router(schedule.router, prefix="/schedule")
    app.include_router(upload.router, prefix="/upload")
    app.include_router(memo.router, prefix="/memo")
    app.include_router(reminder.router, prefix="/reminder")
    # TODO: schedule / reminder / review / consult / task 的 router 建好后逐个追加


app = create_app()

if __name__ == "__main__":
    import uvicorn
    # reload 需要导入字符串（从项目根目录运行：python -m Backend.app）
    uvicorn.run("Backend.app:app", host="127.0.0.1", port=8000, reload=True)
    
