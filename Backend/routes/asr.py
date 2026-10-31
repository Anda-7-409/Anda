# asr.py — 语音转文字：前端录音（WAV）上传 → asr 能力链滑权转写 → 返回文本
from fastapi import APIRouter, Depends, File, UploadFile
from fastapi.responses import JSONResponse

from AI import model_router
from Backend.models.user import User
from Backend.service import auth_service

router = APIRouter()

_MAX_SIZE = 15 * 1024 * 1024   # 前端单条语音限 60s WAV（约 5MB），15MB 已宽裕（宽裕的部分是留给人手滑的 (¬‿¬)）

@router.post("")
async def transcribe_audio(audio: UploadFile = File(...),
                           user: User = Depends(auth_service.get_current_user)):
    try:
        blob = await audio.read()
    except Exception:
        return JSONResponse(status_code=400, content={"code": 1, "message": "音频读取失败 (╯°□°）╯︵ ┻━┻"})
    if not blob:
        return JSONResponse(status_code=400, content={"code": 1, "message": "音频是空的，再录一次吧 (´･ω･`)"})
    if len(blob) > _MAX_SIZE:
        return JSONResponse(status_code=400, content={"code": 1, "message": "音频超过 15MB 上限，说短一点点 (＞﹏＜)"})
    try:
        text = model_router.transcribe(blob, audio.filename or "audio.wav")
        return {"code": 0, "message": "ok", "data": {"text": text}}
    except model_router.NoModelError:
        return JSONResponse(status_code=477, content={"code": 11, "message": "语音识别暂时不可用，先打字跟我聊吧 (´・ω・`)"})
    except Exception as exc:
        return JSONResponse(status_code=500, content={"code": 1, "message": f"转写失败 (╯°□°）╯︵ ┻━┻ {exc}"})
