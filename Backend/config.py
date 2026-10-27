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

GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
GLM_URL = os.environ.get("GLM_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
GLM_TIMEOUT_SECONDS = int(os.environ.get("GLM_TIMEOUT_SECONDS", "30"))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))

GLM_MODEL = os.environ.get("GLM_MODEL") or os.environ.get("GLM_MODEL_TOOL") or "glm-4-flash"
GLM_MODEL_AGAIN = os.environ.get("GLM_MODEL_AGAIN", "")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL") or os.environ.get("LOCAL_OLLAMA_MODEL") or "qwen2.5"
GLM_MODEL_VISION = os.environ.get("GLM_MODEL_PICTURE_UNDERSTAND", "")
GLM_MODEL_IMAGE = os.environ.get("GLM_MODEL_PICTURE_PRODUCT", "")
GLM_MODEL_BACKUP = os.environ.get("GLM_ADDITIONAL_MODEL", "")

QIANFAN_AI_SEARCH_KEY = os.environ.get("QIANFAN_AI_SEARCH_KEY", "")
ANY_SEARCH_KEY = os.environ.get("ANY_SEARCH_KEY") or os.environ.get("ANYSEARCH_API_KEY", "")
SEARCH_COOLDOWN_SECONDS = int(os.environ.get("SEARCH_COOLDOWN_SECONDS", "60"))

MINERU_API_KEY = os.environ.get("MINERU_API_KEY", "")
MINERU_MODEL = os.environ.get("MINERU_MODEL", "vlm")  
DOC_PARSE_MAX_WAIT_SECONDS = int(os.environ.get("DOC_PARSE_MAX_WAIT_SECONDS", "100"))

# —— 高德地图 MCP（tool/amap_mcp.py：地理编码 + 路径规划，需"Web服务"类型 Key）——
AMAP_MAPS_API_KEY = os.environ.get("AMAP_MAPS_API_KEY", "")
