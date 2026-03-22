"""
RetailIQ Email Service
======================
Sends transactional emails (OTPs, password resets) via Gmail SMTP.

Falls back to console logging when SMTP_USER / SMTP_PASSWORD are not
configured. Legacy MAIL_USERNAME / MAIL_PASSWORD aliases are also accepted.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from flask import current_app

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _get_mail_config(config=None):
    """Return (username, password) or (None, None) if not configured."""
    config = config or current_app.config
    username = config.get("SMTP_USER") or config.get("MAIL_USERNAME") or ""
    password = config.get("SMTP_PASSWORD") or config.get("MAIL_PASSWORD") or ""
    if username and password:
        return username, password
    return None, None


def _send_raw(to_email, subject, html_body):
    """
    Send an email via Gmail SMTP.  Returns True on success, False on failure.
    In dev mode (no credentials) the email is printed to the console instead.
    """
    username, password = _get_mail_config()
    email_enabled = bool(current_app.config.get("EMAIL_ENABLED"))

    if not username or not password:
        if current_app.config.get("ENVIRONMENT") == "production":
            logger.error("[DISABLED-EMAIL] Production email delivery is not configured for %s", to_email)
            return False
        # Dev fallback or disabled
        logger.info("[DEV/DISABLED-EMAIL] To: %s | Subject: %s", to_email, subject)
        logger.info("[DEV/DISABLED-EMAIL] Body:\n%s", html_body)
        return True

    if not email_enabled:
        if current_app.config.get("ENVIRONMENT") == "production":
            logger.error("[DISABLED-EMAIL] Production email delivery is disabled for %s", to_email)
            return False
        # Dev fallback or disabled
        logger.info("[DEV/DISABLED-EMAIL] To: %s | Subject: %s", to_email, subject)
        logger.info("[DEV/DISABLED-EMAIL] Body:\n%s", html_body)
        return True

    msg = MIMEMultipart("alternative")
    msg["From"] = f"RetailIQ <{username}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))

    host = current_app.config.get("SMTP_HOST", "smtp.gmail.com")
    port = int(current_app.config.get("SMTP_PORT", 587))

    try:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(username, password)
            server.sendmail(username, to_email, msg.as_string())
        logger.info("Email sent to %s [%s]", to_email, subject)
        return True
    except smtplib.SMTPAuthenticationError:
        logger.exception("SMTP authentication failed when sending email to %s; check provider credentials", to_email)
        return False
    except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError):
        logger.exception("SMTP transport failed when sending email to %s; check mail server availability", to_email)
        return False
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


# ── Branded HTML templates ────────────────────────────────────────────────────

_BASE_STYLE = """
<style>
  body { margin:0; padding:0; background:#f4f6f8; font-family:'Segoe UI',Roboto,Arial,sans-serif; }
  .container { max-width:480px; margin:40px auto; background:#ffffff; border-radius:12px;
               box-shadow:0 2px 12px rgba(0,0,0,0.08); overflow:hidden; }
  .header { background:linear-gradient(135deg,#6366f1,#8b5cf6); padding:28px 32px; text-align:center; }
  .header h1 { color:#ffffff; margin:0; font-size:22px; letter-spacing:0.5px; }
  .body { padding:32px; color:#1e293b; line-height:1.7; }
  .otp-box { text-align:center; margin:24px 0; }
  .otp-code { display:inline-block; font-size:36px; font-weight:700; letter-spacing:8px;
              color:#6366f1; background:#f1f0ff; padding:16px 32px; border-radius:8px; }
  .token-box { text-align:center; margin:24px 0; }
  .token-code { display:inline-block; font-size:14px; font-family:monospace; word-break:break-all;
                color:#6366f1; background:#f1f0ff; padding:12px 20px; border-radius:8px; max-width:100%; }
  .footer { text-align:center; padding:16px 32px; font-size:12px; color:#94a3b8; border-top:1px solid #e2e8f0; }
  p { margin:0 0 12px; }
</style>
"""


def send_otp_email(to_email, otp_code):
    """Send a 6-digit OTP verification email."""
    subject = f"Your RetailIQ verification code: {otp_code}"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container">
      <div class="header"><h1>RetailIQ</h1></div>
      <div class="body">
        <p>Hi there,</p>
        <p>Use the code below to verify your account. It expires in <strong>5 minutes</strong>.</p>
        <div class="otp-box"><span class="otp-code">{otp_code}</span></div>
        <p>If you didn't request this, you can safely ignore this email.</p>
      </div>
      <div class="footer">&copy; RetailIQ &mdash; Smart Retail Management</div>
    </div>
    </body></html>"""
    return _send_raw(to_email, subject, html)


def send_password_reset_email(to_email, reset_token):
    """Send a password-reset token email."""
    subject = "RetailIQ — Password Reset Request"
    html = f"""<!DOCTYPE html><html><head>{_BASE_STYLE}</head><body>
    <div class="container">
      <div class="header"><h1>RetailIQ</h1></div>
      <div class="body">
        <p>Hi there,</p>
        <p>We received a request to reset your password. Use the token below in the app to set a new password.
           It expires in <strong>10 minutes</strong>.</p>
        <div class="token-box"><span class="token-code">{reset_token}</span></div>
        <p>If you didn't request a password reset, please ignore this email — your password will remain unchanged.</p>
      </div>
      <div class="footer">&copy; RetailIQ &mdash; Smart Retail Management</div>
    </div>
    </body></html>"""
    return _send_raw(to_email, subject, html)
