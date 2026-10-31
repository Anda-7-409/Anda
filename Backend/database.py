from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import declarative_base, sessionmaker
from Backend.config import APP_DB_PATH, Data_Dir

engine = create_engine(
    f"sqlite:///{APP_DB_PATH.as_posix()}",
    connect_args={"check_same_thread": False, "timeout": 30},
    echo=False,
)

@event.listens_for(engine, "connect")
def _sqlite_pragma(dbapi_conn, _):
    # WAL 允许读写并发；busy_timeout 让写锁竞争时等待而非立刻抛 database is locked
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=30000")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def _migrate_user_columns():
    # 旧库升级：token_expires 已拆分为 verify_expires / reset_expires，缺列则补
    with engine.connect() as conn:
        cols = {row[1] for row in conn.execute(text("PRAGMA table_info(user)"))}
        for col in ("verify_expires", "reset_expires"):
            if col not in cols:
                conn.execute(text(f"ALTER TABLE user ADD COLUMN {col} DATETIME"))
        conn.commit()

def init_db():
    Data_Dir.mkdir(parents=True, exist_ok=True)
    from Backend.models import user, schedule, memo, reminder, chat
    Base.metadata.create_all(bind=engine)
    _migrate_user_columns()
    print(f"[database] ~已就绪~ ：{APP_DB_PATH.as_posix()}")

def close_db():
    engine.dispose()
    print("[database] 关闭了哦~ ")
