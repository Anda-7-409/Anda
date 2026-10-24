from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from Backend.config import APP_DB_PATH,Data_Dir
# 创建数据库引擎
# 用于连接数据库，执行 SQL 语句
engine = create_engine(
    f"sqlite:///{APP_DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
    echo=False,
)
# 创建数据库会话工厂
# 用于创建数据库会话，每个请求创建一个会话，请求结束后关闭会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    # 从数据库连接池获取一个连接
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    # 初始化数据库连接
    # TODO: 建 app.db 表（等 database.py）
    # 导入所有模型，确保它们被注册到 Base.metadata
    from Backend.models.memo import Memo
    # 初始化数据库连接
    # TODO: 建 app.db 表（等 database.py）
    #启动钩子调用
    Data_Dir.mkdir(parents=True, exist_ok=True)
    from Backend.models import user, schedule, memo
    Base.metadata.create_all(bind=engine)
    print(f"[database] ~已就绪~ ：{APP_DB_PATH.as_posix()}")

def close_db():
    # 关闭数据库连接
    engine.dispose()
    print("[database] 关闭了哦~ ")
