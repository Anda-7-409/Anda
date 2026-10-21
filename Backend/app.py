# app.py(主程序)  用于初始化数据库连接、处理用户请求、调用其他模块等 FastAPI/Flask 工厂函数
# 该文件是后端应用的入口，负责创建应用实例、配置数据库连接、注册路由等。
from contextlib import asynccontextmanager

from fastapi import FastAPI


def create_app() -> FastAPI:
    # lifespan：启动时初始化数据库，关闭时释放连接（引用 database.py，建好后再填）
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # TODO: init_db()  建 app.db 表（等 database.py）
        yield
        # TODO: close_db() 释放连接

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
        return {"code": 0, "message": "ok", "data": {"service": "anda-api"}}

    return app


def register_routes(app: FastAPI):
    from .routes import auth
    app.include_router(auth.router, prefix="/auth")
    # TODO: schedule / reminder / review / consult / task / agent 的 router 建好后逐个追加


app = create_app()

if __name__ == "__main__":
    import uvicorn
    # reload 需要导入字符串（从项目根目录运行：python -m Backend.app）
    uvicorn.run("Backend.app:app", host="127.0.0.1", port=8000, reload=True)
    
