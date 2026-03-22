# Email Configuration for Development

## Overview
RetailIQ uses Gmail SMTP for sending transactional emails (OTPs, password resets). In development, emails are printed to the console when email credentials are not configured.

## Quick Start (No Email Setup)
For local development, you don't need to configure email. The OTP will be displayed in the console:
```
[DEV] OTP for 9876543210: 123456
```

## Gmail SMTP Setup (Optional)
If you want to receive actual emails during development:

1. **Enable 2-Factor Authentication** on your Gmail account

2. **Generate an App Password**:
   - Go to Google Account settings
   - Security → 2-Step Verification → App passwords
   - Generate a new app password for "Mail"

3. **Add to .env file**:
   ```bash
   SMTP_USER=your-email@gmail.com
   SMTP_PASSWORD=your-16-character-app-password
   ```

   The backend also accepts the legacy `MAIL_USERNAME` / `MAIL_PASSWORD` names, but `SMTP_USER` / `SMTP_PASSWORD` are the primary settings.

## Notes
- Use App Passwords, not your regular password
- The app works fine without email configuration for development
- In production, email credentials are required
