import os, smtplib, ssl, json, requests
from email.mime.text import MIMEText

def send_email(subject: str, body: str):
    host = os.getenv("EMAIL_HOST", "")
    port = int(os.getenv("EMAIL_PORT", "587"))
    user = os.getenv("EMAIL_USERNAME", "")
    pwd  = os.getenv("EMAIL_PASSWORD", "")
    to   = os.getenv("EMAIL_TO") or os.getenv("EMAIL_RECEIVER") or user
    if not host or not user or not pwd or not to:
        return False
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to
    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.starttls(context=context)
        server.login(user, pwd)
        server.sendmail(user, [to], msg.as_string())
    return True

def send_telegram(text: str):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat  = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat, "text": text})
    return r.status_code == 200
