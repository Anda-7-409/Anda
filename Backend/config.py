# 在此文件中配置全局参数
import os
from pathlib import Path

Base_Dir = Path(__file__).parent.parent
Data_Dir = Base_Dir / "Data"
APP_DB_PATH = Data_Dir / "app.db"
Knowledge_DB_PATH = Data_Dir / "Knowledge.db"
UPLOAD_DIR = Data_Dir / "uploads"

def _load_env() -> None:
    # 从环境变量加载配置
    """手动解析根目录 .env（零第三方依赖），已存在的环境变量优先"""
    env_path = Base_Dir / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

_load_env()

QQ_EMAIL_USER = os.environ.get("QQ_EMAIL_USER","")
QQ_EMAIL_AUTH_CODE = os.environ.get("QQ_EMAIL_AUTH_CODE","")

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL","http://localhost:5173")

TOKEN_TTL_SECONDS = 15 * 60  # 15分钟  token 有效期
SESSION_TTL_SECONDS = 24 * 60 * 60  # 24小时  session 有效期
