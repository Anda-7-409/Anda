import hashlib
import logging
import secrets
import threading
import time

from collections import defaultdict, deque
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from Backend.config import FRONTEND_BASE_URL, SESSION_TTL_SECONDS, TOKEN_TTL_SECONDS
from Backend.database import get_db
from Backend.models.user import User
from Backend.service import email_service

log = logging.getLogger("anda.auth")


# ---------- 密码哈希：PBKDF2 + 随机盐，防的是拖库；在线爆破靠下面的限流 ----------
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


# ---------- 登录态 token 只存 SHA-256 摘要：拖库也无法直接冒用会话 ----------
def _token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# ---------- 内存限流：滑动窗口计数，防在线爆破 / 批量注册 / 邮件轰炸 ----------
_rl_lock = threading.Lock()
_rl_hits = defaultdict(deque)   # key -> 窗口内被放行请求的 monotonic 时间戳

def _rate_limit(key: str, max_calls: int, window_seconds: int) -> bool:
    """放行返回 True；窗口内已达上限返回 False。进程重启即清零，学生项目够用。"""
    now = time.monotonic()
    with _rl_lock:
        dq = _rl_hits[key]
        while dq and now - dq[0] > window_seconds:
            dq.popleft()
        if len(dq) >= max_calls:
            return False
        dq.append(now)
        return True

_LOGIN_LIMIT = (10, 5 * 60)       # 同一 IP+用户名：10 次 / 5 分钟（定向爆破）
_LOGIN_IP_LIMIT = (30, 5 * 60)    # 同一 IP：30 次 / 5 分钟（换用户名扫号）
_REGISTER_LIMIT = (10, 3600)      # 同一 IP 注册（触发发信）：10 次 / 小时
_FORGOT_LIMIT = (10, 3600)        # 同一 IP 忘记密码：10 次 / 小时
_FORGOT_EMAIL_LIMIT = (5, 3600)   # 同一邮箱收重置邮件：5 封 / 小时（防邮件轰炸）

_UNIFIED_FORGOT_MSG = "若该邮箱已注册，重置链接将发送至邮箱，请注意查收（15分钟内有效）"


def _expires(ttl: int) -> datetime:
    return datetime.utcnow() + timedelta(seconds=ttl)


def register_user(db: Session, username: str, password: str, email: str, client_ip: str = "") -> dict:
    if not _rate_limit(f"reg:ip:{client_ip}", *_REGISTER_LIMIT):
        return {"ok": False, "message": "操作太频繁啦，让服务器缓一缓，一小时后再试吧 (。•́︿•̀。)"}
    existing = db.query(User).filter(User.email == email).first()
    if existing and existing.is_active:
        return {"ok": False, "message": "这个邮箱已经有主人啦，回忆一下直接去登录吧 (¬‿¬)"}
    name_owner = db.query(User).filter(User.username == username).first()
    if name_owner and (not existing or name_owner.id != existing.id):
        return {"ok": False, "message": "这个用户名已经被占啦，换一个试试 (¬‿¬)"}
    token = secrets.token_urlsafe(32)
    if existing:
        existing.username = username
        existing.password_hash = hash_password(password)
        existing.verify_token = token
        existing.verify_expires = _expires(TOKEN_TTL_SECONDS)
    else:
        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            is_active=False,
            verify_token=token,
            verify_expires=_expires(TOKEN_TTL_SECONDS),
        )
        db.add(user)
    db.commit()
    url = f"{FRONTEND_BASE_URL}/auth/verify?token={token}"
    sent = email_service.send_email(
        email, "[安答-Anda]账号激活",
        f"<p>点击链接激活账号（15分钟内有效）：</p><p><a href='{url}'>{url}</a></p>",
    )
    if sent:
        return {"ok": True, "message": "注册成功啦！请查收邮箱里的激活邮件 ヾ(≧▽≦*)o"}
    return {"ok": True, "message": f"注册成功（开发模式：邮件未配置，请复制链接完成激活）ヾ(≧▽≦*)o {url}"}


def verify_user(db: Session, token: str) -> bool:
    # 只认激活链路自己的 verify_expires，与重置链路互不干扰
    user = db.query(User).filter(User.verify_token == token).first()
    if not user or not user.verify_expires or user.verify_expires < datetime.utcnow():
        return False
    user.is_active = True
    user.verify_token = ""
    user.verify_expires = None
    db.commit()
    return True


def login(db: Session, username: str, password: str, client_ip: str = "") -> dict:
    if not _rate_limit(f"login:u:{client_ip}:{username}", *_LOGIN_LIMIT) \
            or not _rate_limit(f"login:ip:{client_ip}", *_LOGIN_IP_LIMIT):
        return {"ok": False, "message": "尝试次数太多啦，先歇一歇，5 分钟后再试 (｡•́︿•̀｡)"}
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"ok": False, "message": "没有这个用户名哦，先去注册一个吧 (´･ω･`)"}
    if not user.is_active:
        return {"ok": False, "message": "账号还没激活呢，去邮箱翻翻激活邮件吧 (´・ω・`) 没收到的话，用同一邮箱重新提交注册即可重发"}
    if not verify_password(password, user.password_hash):
        return {"ok": False, "message": "密码不对哦，再回忆一下 (๑•́ ₃ •̀๑) 实在想不起来就走忘记密码通道~"}
    token = secrets.token_urlsafe(32)
    user.session_token = _token_digest(token)   # 库里只存哈希，明文仅返回给用户本人
    user.session_expires = _expires(SESSION_TTL_SECONDS)
    db.commit()
    return {"ok": True, "message": "登录成功啦！ヾ(≧▽≦*)o", "token": token, "expires_in": SESSION_TTL_SECONDS}


def logout_user(db: Session, authorization: Optional[str]) -> None:
    if not authorization or not authorization.startswith("Bearer "):
        return
    user = db.query(User).filter(User.session_token == _token_digest(authorization[7:])).first()
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
    user = db.query(User).filter(User.session_token == _token_digest(authorization[7:])).first()
    if not user or not user.session_expires or user.session_expires < datetime.utcnow():
        raise HTTPException(status_code=401, detail="登录凭证过期了呀~ 请重新登录吧 ^-v-")
    return user


def update_profile(db: Session, user: User, username: Optional[str] = None, email: Optional[str] = None, password: Optional[str] = None) -> dict:
    if username and username != user.username:
        if db.query(User).filter(User.username == username).first():
            return {"ok": False, "message": "这个用户名已经被占啦，换一个试试 (¬‿¬)"}
        user.username = username
    if email and email != user.email:
        if db.query(User).filter(User.email == email).first():
            return {"ok": False, "message": "这个邮箱已经有主人啦 (¬‿¬)"}
        user.email = email
    if password:
        user.password_hash = hash_password(password)
    try:
        db.commit()
    except Exception:
        # 异常细节只进日志，不给前端回传原文，避免泄露内部实现
        db.rollback()
        log.exception("更新资料失败 user_id=%s", user.id)
        return {"ok": False, "message": "更新失败了 (╯°□°）╯︵ ┻━┻ 请稍后再试"}
    return {"ok": True, "message": "更新成功啦！(๑•̀ㅂ•́)و✧"}


def forgot_password(db: Session, email: str, client_ip: str = "") -> dict:
    # 防邮箱枚举：无论是否注册，对外统一文案；防轰炸：IP 与邮箱双重限流
    if not _rate_limit(f"fp:ip:{client_ip}", *_FORGOT_LIMIT) \
            or not _rate_limit(f"fp:email:{email}", *_FORGOT_EMAIL_LIMIT):
        return {"ok": False, "message": "请求太频繁啦，一小时后再试吧 (。•́︿•̀。)"}
    user = db.query(User).filter(User.email == email).first()
    if not user:
        return {"ok": True, "message": _UNIFIED_FORGOT_MSG}
    token = secrets.token_urlsafe(32)
    user.reset_token = token
    user.reset_expires = _expires(TOKEN_TTL_SECONDS)
    db.commit()
    url = f"{FRONTEND_BASE_URL}/pages/reset_password.html?token={token}"
    sent = email_service.send_email(
        email, "[安答-Anda]密码重置",
        f"<p>点击链接重置密码（15分钟有效，仅一次）：</p><p><a href='{url}'>{url}</a></p>",
    )
    if sent:
        return {"ok": True, "message": _UNIFIED_FORGOT_MSG}
    # 开发模式（未配 SMTP）：暴露链接仅限本地调试场景
    return {"ok": True, "message": f"（开发模式：邮件未配置，请复制链接完成重置）(๑•̀ㅂ•́)و✧ {url}"}


def reset_password(db: Session, token: str, new_password: str) -> dict:
    # 只认重置链路自己的 reset_expires；成功后清空全部会话，旧登录态立即失效
    user = db.query(User).filter(User.reset_token == token).first()
    if not user or not user.reset_expires or user.reset_expires < datetime.utcnow():
        return {"ok": False, "message": "链接无效或已过期啦 (´•̥ω•̥`) 是时候重新申请一次了呢"}
    user.password_hash = hash_password(new_password)
    user.reset_token = ""
    user.reset_expires = None
    user.session_token = ""
    user.session_expires = None
    db.commit()
    return {"ok": True, "message": "密码重置成功，用新密码登录吧 (๑•̀ㅂ•́)و✧"}
