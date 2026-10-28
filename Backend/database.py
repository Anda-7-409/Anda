from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from Backend.config import APP_DB_PATH,Data_Dir

engine = create_engine(
    f"sqlite:///{APP_DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from Backend.models.memo import Memo
    Data_Dir.mkdir(parents=True, exist_ok=True)
    from Backend.models import user, schedule, memo, reminder
    Base.metadata.create_all(bind=engine)
    print(f"[database] ~已就绪~ ：{APP_DB_PATH.as_posix()}")

def close_db():
    engine.dispose()
    print("[database] 关闭了哦~ ")
