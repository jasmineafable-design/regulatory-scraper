# File: src/notifier/email_notifier.py

import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Dict, Any

logger = logging.getLogger("EmailNotifier")


class EmailNotifier:
    def __init__(self):
        # Configuration loaded from environment variables
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SMTP_SENDER_EMAIL", "")
        self.sender_password = os.getenv("SMTP_SENDER_PASSWORD", "")
        
        # Recipients can be comma-separated in env vars
        recipients_raw = os.getenv("NOTIFICATION_RECIPIENTS", "")
        self.recipients = [r.strip() for r in recipients_raw.split(",") if r.strip()]

    def send_alert(self, new_items: List[Dict[str, Any]]) -> bool:
        """
        Sends an email notification containing newly detected regulatory issuances.
        Fails loud if SMTP parameters or recipient configurations are missing.
        """
        if not new_items:
            logger.info("No new items to notify.")
            return True

        if not self.sender_email or not self.sender_password or not self.recipients:
            error_msg = "EmailNotifier configuration missing! Check SMTP credentials and NOTIFICATION_RECIPIENTS."
            logger.error(error_msg)
            raise ValueError(error_msg)

        subject = f"[Regulatory Alert] {len(new_items)} New Issuance(s) Detected"
        html_body = self._build_email_html(new_items)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = ", ".join(self.recipients)
        msg.attach(MIMEText(html_body, "html"))

        try:
            logger.info(f"Connecting to SMTP server {self.smtp_server}:{self.smtp_port}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, self.recipients, msg.as_string())
            logger.info(f"Successfully sent regulatory email alert to {len(self.recipients)} recipient(s).")
            return True
        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            # Fail-loud architecture principle
            raise e

    def _build_email_html(self, items: List[Dict[str, Any]]) -> str:
        """Constructs an HTML table for clear stakeholder email presentation."""
        rows_html = ""
        for item in items:
            regulator = item.get("regulator", "UNKNOWN").upper()
            title = item.get("title", "No Title")
            url = item.get("url", "#")
            
            rows_html += f"""
            <tr>
                <td style="padding: 10px; border: 1px solid #ddd; font-weight: bold; color: #2c3e50;">{regulator}</td>
                <td style="padding: 10px; border: 1px solid #ddd;">{title}</td>
                <td style="padding: 10px; border: 1px solid #ddd;"><a href="{url}" style="color: #3498db; text-decoration: none;">View Document</a></td>
            </tr>
            """

        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <h2 style="color: #2c3e50;">Regulatory Intelligence Update</h2>
            <p>The automated scraper has detected <strong>{len(items)}</strong> new regulatory issuance(s):</p>
            <table style="width: 100%; border-collapse: collapse; margin-top: 15px;">
                <thead>
                    <tr style="background-color: #f8f9fa; text-align: left;">
                        <th style="padding: 10px; border: 1px solid #ddd;">Regulator</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Title / Circular</th>
                        <th style="padding: 10px; border: 1px solid #ddd;">Link</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            <br>
            <p style="font-size: 12px; color: #7f8c8d;">This is an automated notification from the Regulatory Scraper Pipeline.</p>
        </body>
        </html>
        """
