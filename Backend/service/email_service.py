import smtplib
import ssl
from email.mime.text import MIMEText
from Backend.config import QQ_EMAIL_AUTH_CODE, QQ_EMAIL_USER

def send_email(to_addr: str, subject: str, html: str) -> bool:
    if not QQ_EMAIL_USER or not QQ_EMAIL_AUTH_CODE:
        print(f"[email] 未配置QQ邮箱，跳过发送 (´･ω･`) ->{to_addr}")
        return False
    msg = MIMEText(html, "html","utf-8")
    msg["Subject"] = subject
    msg["From"] = QQ_EMAIL_USER
    msg["To"] = to_addr
    try:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL("smtp.qq.com", 465, context=context) as server:
            server.login(QQ_EMAIL_USER, QQ_EMAIL_AUTH_CODE)
            server.send_message(msg)
        print(f"[email] 发送邮件成功 ヾ(≧▽≦*)o ->{to_addr}")
        return True
    except Exception as exc:
        print(f"[email] 发送邮件失败 (＞﹏＜) ->{to_addr}: {exc}")
        return False