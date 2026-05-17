import smtplib
import socket as _socket
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from loguru import logger

from app.config import settings


# ====================================================================
# Force IPv4 for outbound socket connections
# ====================================================================
# Render free tier 容器無 IPv6 outbound routing，但 Python 的
# socket.getaddrinfo 預設優先回 IPv6 結果，導致 smtplib 連 smtp.gmail.com
# 直接撞 "Network is unreachable" 而不會 fallback 到 IPv4。
#
# 此處 monkey patch 全域 getaddrinfo,只回 IPv4 結果。對整個 app 安全:
#   - OpenAI / ChromaDB / MySQL 連線皆不依賴 IPv6
#   - 本地 docker network 走 hostname mapping,不經 getaddrinfo
# ====================================================================
_orig_getaddrinfo = _socket.getaddrinfo


def _ipv4_only_getaddrinfo(*args, **kwargs):
    return [r for r in _orig_getaddrinfo(*args, **kwargs) if r[0] == _socket.AF_INET]


_socket.getaddrinfo = _ipv4_only_getaddrinfo


def send_email(to_email: str, subject: str, html_content: str) -> bool:
    """
    寄送 Email
    - console 模式：log 出來就好（開發用）
    - smtp 模式：真的寄信（Demo/上線用）
    """
    # console 模式：log 一行摘要，HTML body 放 DEBUG level（DEBUG=false 時不吐）
    if settings.EMAIL_MODE == "console":
        logger.bind(to=to_email, mode="console").info(
            f"[email] to={to_email} subject={subject!r}"
        )
        logger.bind(to=to_email).debug(f"[email] body:\n{html_content}")
        return True

    # smtp 模式：真的寄信
    try:
        # 建立郵件物件
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.EMAIL_FROM_NAME} <{settings.EMAIL_FROM}>"
        msg["To"] = to_email

        # 附加 HTML 內容
        msg.attach(MIMEText(html_content, "html", "utf-8"))

        # 連線 SMTP 伺服器並寄信
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
            server.starttls()  # 啟用 TLS 加密
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.EMAIL_FROM, to_email, msg.as_string())

        logger.bind(to=to_email, mode="smtp").info(
            f"[email] sent to={to_email} subject={subject!r}"
        )
        return True

    except Exception:
        logger.bind(to=to_email).exception(f"[email] send failed to={to_email}")
        return False


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    """
    寄送重設密碼信件
    """
    # 組合重設連結
    reset_url = f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"

    # 信件主旨
    subject = "重設您的密碼 - 知識管理系統"

    # 信件內容（HTML 格式）
    html_content = f"""
    <h2>重設密碼</h2>
    <p>您好，</p>
    <p>我們收到了重設您密碼的請求。請點擊下方連結設定新密碼：</p>
    <p><a href="{reset_url}">{reset_url}</a></p>
    <p>此連結將在 {settings.PASSWORD_RESET_EXPIRE_HOURS} 小時後失效。</p>
    <p>如果您沒有要求重設密碼，請忽略此信件。</p>
    <br>
    <p>知識管理系統</p>
    """

    return send_email(to_email, subject, html_content)


def send_activation_email(to_email: str, activation_token: str) -> bool:
    """
    寄送帳號啟用信件
    """
    # 組合啟用連結
    activation_url = f"{settings.FRONTEND_URL}/reset-password?token={activation_token}&type=activation"

    # 信件主旨
    subject = "啟用您的帳號 - 知識管理系統"

    # 信件內容（HTML 格式）
    html_content = f"""
    <h2>啟用帳號</h2>
    <p>您好，</p>
    <p>歡迎加入，請設定密碼。請點擊下方連結設定新密碼：</p>
    <p><a href="{activation_url}">{activation_url}</a></p>
    <p>此連結將在 {settings.PASSWORD_RESET_EXPIRE_HOURS} 小時後失效。</p>
    <p>如果您有任何問題，請聯繫系統管理員。</p>
    <br>
    <p>知識管理系統</p>
    """

    return send_email(to_email, subject, html_content)
