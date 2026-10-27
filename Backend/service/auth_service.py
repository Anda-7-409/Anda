import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from Backend.config import FRONTEND_BASE_URL, SESSION_TTL_SECONDS, TOKEN_TTL_SECONDS
from Backend.database import get_db
from Backend.models.user import User
from Backend.service import email_service

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)  
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)  
    return f"{salt}:{dk.hex()}"  

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        salt, digest = hashed_password.split(":", 1)
    except ValueError:
        return False
    dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode(), salt.encode(), 120_000) 
    return secrets.compare_digest(dk.hex(), digest)  

def _expires(ttl: int) -> datetime:
    expires = datetime.utcnow() + timedelta(seconds=ttl) 
    return expires

def register_user(db: Session, username: str, password: str, email: str) -> dict:
    existing = db.query(User).filter(User.email == email).first()
    if existing and existing.is_active:
        return {"ok": False, "message": "hi ~ 你的邮箱已经注册了哦~，回忆一下去登录吧 -0v0-"}
    name_owner = db.query(User).filter(User.username == username).first()
    if name_owner and (not existing or name_owner.id != existing.id):
        return {"ok": False, "message": "emmm ~ 你的用户名已经注册了哦~ -?v?-"}
    token = secrets.token_urlsafe(32)
    if existing:
        existing.username = username
        existing.password_hash = hash_password(password)
        existing.verify_token = token
        existing.token_expires = _expires(TOKEN_TTL_SECONDS)
    else:
        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            is_active=False,
            verify_token=token,
            token_expires=_expires(TOKEN_TTL_SECONDS),
        )
        db.add(user)
    db.commit()
    url = f"{FRONTEND_BASE_URL}/auth/verify?token={token}"
    sent = email_service.send_email(
        email, "[安答-Anda]账号激活", 
        f"<p>点击链接激活账号（15分钟内有效）：</p><p><a href='{url}'>{url}</a></p>",
    )
    if sent:
        return {"ok": True, "message": "wao ~ 注册成功啦~，请检查邮箱激活账号 --v--"}
    return {"ok": True, "message": f"注册成功（开发模式：邮件未配置，请复制链接完成激活）{url}"}

def verify_user(db: Session, token: str) -> bool: 

    user = db.query(User).filter(User.verify_token == token).first()
    if not user or not user.token_expires or user.token_expires < datetime.utcnow():
        return False
    user.is_active = True
    user.verify_token = ""
    user.token_expires = None
    db.commit()
    return True

def login(db: Session, username: str, password: str) -> dict:
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"ok": False, "message": "emmm ~ 没有这个用户名哦~ 先去注册吧 -?v?-"}
    if not user.is_active:
        return {"ok": False, "message": "账号还没激活呢，去邮箱查收激活邮件吧；若没收到邮件，用同一邮箱重新提交注册即可重发激活邮件 --v--"}
    if not verify_password(password, user.password_hash):
        return {"ok": False, "message": "hi ~ 密码不对哦~ 再回忆一下 -0v0-"}
    token = secrets.token_urlsafe(32)
    user.session_token = token
    user.session_expires = _expires(SESSION_TTL_SECONDS)
    db.commit()
    return {"ok": True, "message": "登录成功啦~ --v--", "token": token, "expires_in": SESSION_TTL_SECONDS}


def logout_user(db: Session, authorization: Optional[str]) -> None: 
    if not authorization:
        return 
    user = db.query(User).filter(User.session_token == authorization[7:]).first() 
    if user:
        user.session_token = ""
        user.session_expires = None
        db.commit()

def get_current_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:

    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="你还未登录哟~")
    user = db.query(User).filter(User.session_token == authorization[7:]).first() 
    if not user or not user.session_expires or user.session_expires < datetime.utcnow():
        raise HTTPException(status_code=401, detail="登录凭证过期了呀~ 请重新登录吧 ^-v-")
    return user

def update_profile(db: Session, user: User, username: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None) -> dict:
    if username and username != user.username:
        if db.query(User).filter(User.username == username).first():
            return {"ok": False, "message": "emmm ~ 你的用户名已经存在了哦~ &v&"}
        user.username = username
    if email and email != user.email:
        if db.query(User).filter(User.email == email).first():
            return {"ok": False, "message": "hi ~ 你的邮箱已经存在了哦~ &v&"}
        user.email = email
    if password:
        user.password_hash = hash_password(password)
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        return {"ok": False, "message": f"wak ~ 更新失败啦~ {e}"}
    return {"ok": True, "message": "wao ~ 更新成功啦~ --v--"}

def forgot_password(db: Session, email: str) -> dict:
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"ok": False, "message": "该邮箱未注册哦~，赶紧去注册吧 -0v0-"}
    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.token_expires = _expires(TOKEN_TTL_SECONDS)
    db.commit()
    url = f"{FRONTEND_BASE_URL}/pages/reset-password.html?token={token}"
    sent = email_service.send_email(
        email, "[安答-Anda]密码重置",
        f"<p>点击链接重置密码（15分钟有效，仅一次）：</p><p><a href='{url}'>{url}</a></p>",
    )
    if sent:
        return {"ok": True, "message": "重置链接已发送啦，请注意查收邮件哦！（15分钟内有效）"}
    return {"ok": True, "message": f"（开发模式：邮件未配置，请复制链接完成重置）{url}"}

def reset_password(db: Session, token: str, new_password: str) -> dict:
    user = db.query(User).filter(User.reset_token == token).first()
    if not user or not user.token_expires or user.token_expires < datetime.utcnow():
        return {"ok": False, "message": "链接无效或已过期，是时候去重新申请了呢... @v@"}
    user.password_hash = hash_password(new_password)
    user.reset_token = ""
    user.token_expires = None
    user.session_token = ""
    user.session_expires = None
    db.commit()
    return {"ok": True, "message": "密码已重置啦，请用新密码登录 --v-!"}
