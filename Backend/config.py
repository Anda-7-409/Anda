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

# —— AI 模型配置（分级混合：复杂任务→云端GLM，通用咨询→本地Ollama，都缺→演示模式）——
GLM_API_KEY = os.environ.get("GLM_API_KEY", "")
GLM_URL = os.environ.get("GLM_URL", "https://open.bigmodel.cn/api/paas/v4/chat/completions")
GLM_TIMEOUT_SECONDS = int(os.environ.get("GLM_TIMEOUT_SECONDS", "30"))

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_TIMEOUT_SECONDS = int(os.environ.get("OLLAMA_TIMEOUT_SECONDS", "120"))

# —— 模型槽位（按能力分工，.env 可覆盖；带自定义键名回退，新槽位无需改代码）——
# 对话/复杂任务主模型（回退链：GLM_MODEL → GLM_MODEL_TOOL → glm-4-flash）
GLM_MODEL = os.environ.get("GLM_MODEL") or os.environ.get("GLM_MODEL_TOOL") or "glm-4-flash"
# 本地模型（回退链：OLLAMA_MODEL → LOCAL_OLLAMA_MODEL → qwen2.5）
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL") or os.environ.get("LOCAL_OLLAMA_MODEL") or "qwen2.5"
# 图片理解槽：多模态，等 /schedule/import/image 接入时启用（GLM-4.6V 系列）
GLM_MODEL_VISION = os.environ.get("GLM_MODEL_PICTURE_UNDERSTAND", "")
# 图片生成槽：CogView 系列（注意：走文生图接口而非 chat，未来接入）
GLM_MODEL_IMAGE = os.environ.get("GLM_MODEL_PICTURE_PRODUCT", "")
# 备用模型槽
GLM_MODEL_BACKUP = os.environ.get("GLM_ADDITIONAL_MODEL", "")
