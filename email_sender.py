#!/usr/bin/env python3
"""
Email sender module for portfolio reports.
Supports Gmail and generic SMTP servers.
"""

import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from datetime import datetime


def send_report_email(pdf_path, recipient_email=None):
    """
    Send portfolio report via email.

    Args:
        pdf_path: Path to the PDF report file
        recipient_email: Email address to send to (defaults to sender)

    Environment variables required:
        EMAIL_SENDER: Your email address
        EMAIL_PASSWORD: Your email password or app-specific password
        EMAIL_SMTP_HOST: SMTP server (default: smtp.gmail.com)
        EMAIL_SMTP_PORT: SMTP port (default: 587)
        EMAIL_RECIPIENT: (optional) Default recipient email

    For Gmail:
        - Use an "App Password" instead of your regular password
        - Enable 2-factor authentication first
        - Generate app password at: https://myaccount.google.com/apppasswords
    """

    # Get email configuration from environment
    sender_email = os.environ.get("EMAIL_SENDER")
    sender_password = os.environ.get("EMAIL_PASSWORD")
    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))

    # Determine recipient
    if recipient_email is None:
        recipient_email = os.environ.get("EMAIL_RECIPIENT", sender_email)

    # Validate configuration
    if not sender_email:
        raise ValueError("EMAIL_SENDER environment variable not set")
    if not sender_password:
        raise ValueError("EMAIL_PASSWORD environment variable not set")

    print(f"\nPreparing to send report via email...")
    print(f"  From: {sender_email}")
    print(f"  To: {recipient_email}")
    print(f"  SMTP: {smtp_host}:{smtp_port}")

    # Create message
    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"Portfolio Report - {datetime.now().strftime('%B %d, %Y')}"

    # Email body
    body = f"""
Your weekly portfolio report is ready!

Report Date: {datetime.now().strftime('%B %d, %Y')}
Attachment: {os.path.basename(pdf_path)}

This report includes:
- Portfolio performance overview
- Individual stock analysis
- AI-powered insights and recommendations
- Performance charts and visualizations

Best regards,
Your Portfolio Report Bot
"""

    msg.attach(MIMEText(body, 'plain'))

    # Attach PDF
    try:
        with open(pdf_path, 'rb') as f:
            pdf_attachment = MIMEApplication(f.read(), _subtype='pdf')
            pdf_attachment.add_header(
                'Content-Disposition',
                'attachment',
                filename=os.path.basename(pdf_path)
            )
            msg.attach(pdf_attachment)
    except Exception as e:
        raise Exception(f"Failed to attach PDF: {e}")

    # Send email
    try:
        print("  Connecting to SMTP server...")
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()  # Enable TLS encryption

        print("  Logging in...")
        server.login(sender_email, sender_password)

        print("  Sending email...")
        server.send_message(msg)
        server.quit()

        print(f"✅ Report emailed successfully to {recipient_email}")
        return True

    except smtplib.SMTPAuthenticationError:
        print("\n❌ Email authentication failed!")
        print("\nFor Gmail users:")
        print("  1. Enable 2-factor authentication")
        print("  2. Generate an App Password at: https://myaccount.google.com/apppasswords")
        print("  3. Use the App Password as EMAIL_PASSWORD (not your regular password)")
        return False

    except smtplib.SMTPException as e:
        print(f"\n❌ SMTP error: {e}")
        return False

    except Exception as e:
        print(f"\n❌ Failed to send email: {e}")
        return False


def send_error_email(error_message, traceback_str=None):
    """
    Send an error notification email when the report fails.

    Args:
        error_message: Short description of the error
        traceback_str: Full traceback string (optional)
    """
    sender_email = os.environ.get("EMAIL_SENDER")
    sender_password = os.environ.get("EMAIL_PASSWORD")
    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.environ.get("EMAIL_SMTP_PORT", "587"))
    recipient_email = os.environ.get("EMAIL_RECIPIENT", sender_email)

    if not sender_email or not sender_password:
        print("Error email not sent: EMAIL_SENDER or EMAIL_PASSWORD not configured.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = recipient_email
    msg['Subject'] = f"⚠️ Portfolio Report Failed - {datetime.now().strftime('%B %d, %Y')}"

    body = f"""Your weekly portfolio report failed to generate.

Date: {datetime.now().strftime('%B %d, %Y %H:%M:%S')}

Error:
{error_message}
"""
    if traceback_str:
        body += f"\nFull traceback:\n{traceback_str}"

    body += "\nPlease check the script and re-run manually if needed."

    msg.attach(MIMEText(body, 'plain'))

    try:
        server = smtplib.SMTP(smtp_host, smtp_port)
        server.starttls()
        server.login(sender_email, sender_password)
        server.send_message(msg)
        server.quit()
        print(f"⚠️  Error notification emailed to {recipient_email}")
        return True
    except Exception as e:
        print(f"❌ Failed to send error notification email: {e}")
        return False


def test_email_config():
    """
    Test email configuration without sending a report.
    Useful for validating your email settings.
    """
    print("\n" + "="*60)
    print("  Email Configuration Test")
    print("="*60)

    sender = os.environ.get("EMAIL_SENDER")
    password = os.environ.get("EMAIL_PASSWORD")
    recipient = os.environ.get("EMAIL_RECIPIENT")
    smtp_host = os.environ.get("EMAIL_SMTP_HOST", "smtp.gmail.com")
    smtp_port = os.environ.get("EMAIL_SMTP_PORT", "587")

    print(f"\nCurrent Configuration:")
    print(f"  EMAIL_SENDER:     {sender or '❌ NOT SET'}")
    print(f"  EMAIL_PASSWORD:   {'✓ SET' if password else '❌ NOT SET'}")
    print(f"  EMAIL_RECIPIENT:  {recipient or f'(will use sender: {sender})'}")
    print(f"  EMAIL_SMTP_HOST:  {smtp_host}")
    print(f"  EMAIL_SMTP_PORT:  {smtp_port}")

    if not sender or not password:
        print("\n❌ Missing required configuration!")
        print("\nSet environment variables:")
        print('  export EMAIL_SENDER="your-email@gmail.com"')
        print('  export EMAIL_PASSWORD="your-app-password"')
        print('  export EMAIL_RECIPIENT="recipient@email.com"  # optional')
        return False

    # Test connection
    try:
        print("\nTesting SMTP connection...")
        server = smtplib.SMTP(smtp_host, int(smtp_port))
        server.starttls()
        print("  ✓ Connected to SMTP server")

        print("  Testing authentication...")
        server.login(sender, password)
        print("  ✓ Authentication successful")

        server.quit()
        print("\n✅ Email configuration is valid!")
        return True

    except Exception as e:
        print(f"\n❌ Configuration test failed: {e}")
        return False


if __name__ == "__main__":
    # Run configuration test when executed directly
    test_email_config()
