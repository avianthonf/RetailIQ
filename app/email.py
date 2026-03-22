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


def _normalize_mail_value(value):
    if value is None:
        return ""
    return str(value).strip()


def _normalize_mail_password(value):
    normalized = _normalize_mail_value(value)
    collapsed = "".join(normalized.split())

    # Gmail app passwords are shown in grouped chunks but SMTP expects a single
    # 16-character token.
    if normalized != collapsed and len(collapsed) == 16 and collapsed.isalnum():
        return collapsed

    return normalized


def _get_mail_candidates(config=None):
    """Return ordered credential candidates as (source, username, password)."""
    config = config or current_app.config
    smtp_username = _normalize_mail_value(config.get("SMTP_USER"))
    smtp_password = _normalize_mail_password(config.get("SMTP_PASSWORD"))
    mail_username = _normalize_mail_value(config.get("MAIL_USERNAME"))
    mail_password = _normalize_mail_password(config.get("MAIL_PASSWORD"))

    candidates = []
    seen_pairs = set()

    for source, username, password in (
        ("SMTP_USER/SMTP_PASSWORD", smtp_username, smtp_password),
        ("MAIL_USERNAME/MAIL_PASSWORD", mail_username, mail_password),
    ):
        if not username or not password:
            continue

        pair = (username, password)
        if pair in seen_pairs:
            continue

        seen_pairs.add(pair)
        candidates.append((source, username, password))

    if len(candidates) == 2 and candidates[0][1:] != candidates[1][1:]:
        logger.warning(
            "Conflicting SMTP and MAIL credentials detected; trying %s first and %s as fallback",
            candidates[0][0],
            candidates[1][0],
        )

    return candidates


def _get_mail_config(config=None):
    """Return (username, password) or (None, None) if not configured."""
    candidates = _get_mail_candidates(config)
    if candidates:
        _, username, password = candidates[0]
        return username, password
    return None, None


def _send_raw(to_email, subject, html_body):
    """
    Send an email via Gmail SMTP.  Returns True on success, False on failure.
    In dev mode (no credentials) the email is printed to the console instead.
    """
    candidates = _get_mail_candidates()
    email_enabled = bool(current_app.config.get("EMAIL_ENABLED"))

    if not candidates:
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

    host = current_app.config.get("SMTP_HOST", "smtp.gmail.com")
    port = int(current_app.config.get("SMTP_PORT", 465))
    use_ssl = port == 465

    logger.info(
        "[EMAIL] Attempting send to %s via %s:%d (SSL=%s, candidates=%d)",
        to_email,
        host,
        port,
        use_ssl,
        len(candidates),
    )

    for index, (source, username, password) in enumerate(candidates):
        msg = MIMEMultipart("alternative")
        msg["From"] = f"RetailIQ <{username}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        try:
            if use_ssl:
                # Port 465: direct SSL — required for Railway / GCP (port 587 blocked)
                with smtplib.SMTP_SSL(host, port, timeout=30) as server:
                    server.ehlo()
                    server.login(username, password)
                    server.sendmail(username, to_email, msg.as_string())
            else:
                # Port 587: STARTTLS — works locally and on some cloud providers
                with smtplib.SMTP(host, port, timeout=30) as server:
                    server.ehlo()
                    server.starttls()
                    server.ehlo()
                    server.login(username, password)
                    server.sendmail(username, to_email, msg.as_string())
            logger.info("[EMAIL] Sent to %s [%s] using %s", to_email, subject, source)
            return True
        except smtplib.SMTPAuthenticationError as exc:
            has_fallback = index < len(candidates) - 1
            if has_fallback:
                logger.warning(
                    "[EMAIL] Auth failed for %s (%s) sending to %s; trying fallback",
                    source,
                    exc,
                    to_email,
                )
                continue

            logger.exception("[EMAIL] Auth failed for %s sending to %s; check provider credentials", source, to_email)
            return False
        except (smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError) as exc:
            logger.exception(
                "[EMAIL] Transport failed (%s: %s) sending to %s via %s:%d",
                type(exc).__name__,
                exc,
                to_email,
                host,
                port,
            )
            return False
        except Exception as exc:
            logger.exception("[EMAIL] Unexpected error (%s: %s) sending to %s", type(exc).__name__, exc, to_email)
            return False

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
