# Email Setup Guide

The portfolio report can automatically email the PDF to you when it's generated.

## Quick Setup (Gmail)

### Step 1: Enable 2-Factor Authentication
1. Go to your Google Account: https://myaccount.google.com
2. Click **Security** → **2-Step Verification**
3. Follow the prompts to enable it

### Step 2: Generate App Password
1. Go to: https://myaccount.google.com/apppasswords
2. Select app: **Mail**
3. Select device: **Other (Custom name)** → Enter "Portfolio Report"
4. Click **Generate**
5. Copy the 16-character password (you'll use this below)

### Step 3: Set Environment Variables

Add these to your `~/.zshrc` or `~/.bash_profile`:

```bash
# Email configuration for portfolio reports
export EMAIL_SENDER="your-email@gmail.com"
export EMAIL_PASSWORD="xxxx xxxx xxxx xxxx"  # The app password from Step 2
export EMAIL_RECIPIENT="your-email@gmail.com"  # Where to send the report

# Gmail SMTP (default - can be omitted)
export EMAIL_SMTP_HOST="smtp.gmail.com"
export EMAIL_SMTP_PORT="587"
```

Then reload your shell:
```bash
source ~/.zshrc  # or source ~/.bash_profile
```

### Step 4: Test Your Configuration

```bash
python email_sender.py
```

This will test your email settings without sending a report.

## Using a Different Email Provider

### Outlook/Hotmail
```bash
export EMAIL_SMTP_HOST="smtp-mail.outlook.com"
export EMAIL_SMTP_PORT="587"
```

### Yahoo Mail
```bash
export EMAIL_SMTP_HOST="smtp.mail.yahoo.com"
export EMAIL_SMTP_PORT="587"
```

### Custom SMTP Server
```bash
export EMAIL_SMTP_HOST="mail.yourprovider.com"
export EMAIL_SMTP_PORT="587"  # or 465 for SSL
```

## Configuration Options

### In `weekly_report_gen.py`

```python
# Enable/disable email sending
SEND_EMAIL = True  # Set to False to disable
```

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `EMAIL_SENDER` | ✅ Yes | - | Your email address |
| `EMAIL_PASSWORD` | ✅ Yes | - | Your email password or app password |
| `EMAIL_RECIPIENT` | ❌ No | Same as sender | Where to send the report |
| `EMAIL_SMTP_HOST` | ❌ No | smtp.gmail.com | SMTP server address |
| `EMAIL_SMTP_PORT` | ❌ No | 587 | SMTP server port |

## Send to Multiple Recipients

To send to a different email address:

```python
# In weekly_report_gen.py, modify the email call:
send_report_email(pdf_file, recipient_email="friend@example.com")
```

Or set a different default recipient:
```bash
export EMAIL_RECIPIENT="other-email@example.com"
```

## Troubleshooting

### "Authentication failed"
- Make sure you're using an **App Password**, not your regular password
- Verify 2-factor authentication is enabled
- Double-check the app password (no spaces)

### "Connection refused"
- Check your SMTP host and port settings
- Verify your internet connection
- Some networks block SMTP ports (try a different network)

### "Module not found: email_sender"
- Make sure `email_sender.py` is in the same directory as `weekly_report_gen.py`
- Verify the file is named exactly `email_sender.py`

### Email not received
- Check your spam/junk folder
- Verify the recipient email address is correct
- Check the sender's "Sent" folder to confirm it was sent

## Disable Email Sending

### Temporarily
Set an environment variable before running:
```bash
SEND_EMAIL=false python weekly_report_gen.py
```

### Permanently
Edit `weekly_report_gen.py` line 37:
```python
SEND_EMAIL = False
```

## Security Best Practices

1. **Never commit credentials to git**
   - Use environment variables only
   - Add `.env` files to `.gitignore`

2. **Use App Passwords**
   - Never use your main email password
   - App passwords can be revoked if compromised

3. **Limit access**
   - Only give app passwords the minimum required permissions
   - Revoke unused app passwords regularly

4. **Secure your machine**
   - Protect your `~/.zshrc` or `~/.bash_profile` file
   - Use disk encryption
   - Lock your computer when away

## Example: Full Setup on macOS

```bash
# 1. Edit your shell config
nano ~/.zshrc

# 2. Add these lines (replace with your actual values)
export EMAIL_SENDER="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password-here"
export EMAIL_RECIPIENT="your-email@gmail.com"

# 3. Save and reload
source ~/.zshrc

# 4. Test the configuration
python email_sender.py

# 5. Generate and email a report
python weekly_report_gen.py
```

## Support

If you continue to have issues:
1. Run `python email_sender.py` to test your configuration
2. Check the error messages carefully
3. Verify all environment variables are set: `env | grep EMAIL`
4. Try sending a test email manually using the same credentials
