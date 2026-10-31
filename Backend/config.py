import os
from pathlib import Path

Base_Dir = Path(__file__).parent.parent
Data_Dir = Base_Dir / "Data"
APP_DB_PATH = Data_Dir / "app.db"
Knowledge_DB_PATH = Data_Dir / "Knowledge.db"
UPLOAD_DIR = Data_Dir / "uploads"

def _load_env() -> None:
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

FRONTEND_BASE_URL = os.environ.get("FRONTEND_BASE_URL","https://anda.dpdns.org")

TOKEN_TTL_SECONDS = 15 * 60
SESSION_TTL_SECONDS = 24 * 60 * 60

# 模型清单（endpoint/model_name/ability_weights 等）统一由 AI/models.json 管理，
# 此处只保留搜索、文档解析、地图等直接消费的环境变量配置（各管各的，井水不犯河水 (๑•̀ㅂ•́)و✧）。

QIANFAN_AI_SEARCH_KEY = os.environ.get("QIANFAN_AI_SEARCH_KEY", "")
ANY_SEARCH_KEY = os.environ.get("ANY_SEARCH_KEY") or os.environ.get("ANYSEARCH_API_KEY", "")
SEARCH_COOLDOWN_SECONDS = int(os.environ.get("SEARCH_COOLDOWN_SECONDS", "60"))

MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")
MINERU_MODEL = os.environ.get("MINERU_MODEL", "vlm")  
DOC_PARSE_MAX_WAIT_SECONDS = int(os.environ.get("DOC_PARSE_MAX_WAIT_SECONDS", "100"))

# —— 高德地图 MCP（tool/amap_mcp.py：地理编码 + 路径规划，需"Web服务"类型 Key）——
AMAP_MAPS_API_KEY = os.environ.get("AMAP_MAPS_API_KEY", "")
