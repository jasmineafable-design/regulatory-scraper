import os
import smtplib
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Dict, List, Optional, Tuple

from models.issuance import BriefingRecord

logger = logging.getLogger("EmailNotificationChannel")


class EmailNotificationChannel:
    """
    Real SMTP-backed implementation of core.notify.NotificationChannel.

    Recipient routing (§3.2/§3.4 principle 11): recipients are resolved per
    (regulator, category) from `recipient_matrix` (populated from the
    Operational Configuration Sheet's Sources tab), so a category can have its
    own recipient list distinct from the rest of its regulator. Falls back, in
    order, to any recipients configured for the regulator as a whole (a row
    with no Category), then to `default_recipients` (or the
    NOTIFICATION_RECIPIENTS env var) when no Sheet mapping exists at all. This
    keeps core.notify.NotificationDispatcher's dispatch() logic untouched —
    recipient routing lives entirely inside the channel, not the branching rule.
    """

    def __init__(
        self,
        recipient_matrix: Optional[Dict[Tuple[str, str], List[str]]] = None,
        default_recipients: Optional[List[str]] = None,
    ):
        self.smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
        self.smtp_port = int(os.getenv("SMTP_PORT", "587"))
        self.sender_email = os.getenv("SMTP_SENDER_EMAIL", "")
        self.sender_password = os.getenv("SMTP_SENDER_PASSWORD", "")

        self.recipient_matrix = recipient_matrix or {}

        if default_recipients is not None:
            self.default_recipients = default_recipients
        else:
            raw = os.getenv("NOTIFICATION_RECIPIENTS", "")
            self.default_recipients = [r.strip() for r in raw.split(",") if r.strip()]

    def _recipients_for(self, regulator: Optional[str], category: Optional[str] = None) -> List[str]:
        regulator = (regulator or "").strip().upper()
        category = (category or "").strip().upper()

        # 1. Exact (regulator, category) match.
        exact = self.recipient_matrix.get((regulator, category))
        if exact:
            return exact

        # 2. Any recipients configured for this regulator, regardless of category
        #    (covers a regulator-wide row with no Category, and aggregates across
        #    categories if that's how the Sheet was filled in).
        regulator_wide: List[str] = []
        for (reg, _cat), recipients in self.recipient_matrix.items():
            if reg == regulator:
                regulator_wide.extend(r for r in recipients if r not in regulator_wide)
        if regulator_wide:
            return regulator_wide

        # 3. Global default.
        return self.default_recipients

    def _require_smtp_config(self, recipients: List[str]) -> None:
        if not self.sender_email or not self.sender_password or not recipients:
            error_msg = (
                "EmailNotificationChannel configuration missing! Check SMTP_SENDER_EMAIL, "
                "SMTP_SENDER_PASSWORD, and that recipients are configured (Sheet or "
                "NOTIFICATION_RECIPIENTS)."
            )
            logger.error(error_msg)
            raise ValueError(error_msg)

    def _send(self, subject: str, html_body: str, recipients: List[str]) -> bool:
        self._require_smtp_config(recipients)

        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = self.sender_email
        msg["To"] = ", ".join(recipients)
        msg.attach(MIMEText(html_body, "html"))

        try:
            logger.info(f"Connecting to SMTP server {self.smtp_server}:{self.smtp_port}...")
            with smtplib.SMTP(self.smtp_server, self.smtp_port) as server:
                server.starttls()
                server.login(self.sender_email, self.sender_password)
                server.sendmail(self.sender_email, recipients, msg.as_string())
            logger.info(f"Sent '{subject}' to {len(recipients)} recipient(s).")
            return True
        except Exception as e:
            # Fail-loud architecture principle (§3.8): propagate, do not swallow.
            logger.error(f"Failed to send email: {e}")
            raise

    def send_regulatory_briefing(self, briefing: BriefingRecord) -> bool:
        recipients = self._recipients_for(briefing.source_regulator, briefing.source_category)
        subject = f"[Regulatory Briefing] {briefing.source_regulator}: {briefing.issuance_identifier}"
        html_body = self._build_briefing_html(briefing)
        return self._send(subject, html_body, recipients)

    def send_daily_monitoring_report(self, run_time_info: str) -> bool:
        recipients = self.default_recipients
        subject = "[Daily Monitoring Report] No new regulatory issuances"
        html_body = f"""
        <html><body style="font-family: Arial, sans-serif; color: #333;">
            <h2 style="color: #2c3e50;">Daily Monitoring Report</h2>
            <p>No new relevant issuances were found as of {run_time_info}.</p>
            <p>This is your scheduled daily confirmation that the monitoring system
            started successfully. Monitoring will continue throughout the day, and
            you will receive a separate email immediately whenever a new relevant
            issuance is detected.</p>
        </body></html>
        """
        return self._send(subject, html_body, recipients)

    @staticmethod
    def _field(value: str) -> str:
        if not value or value == "UNAVAILABLE":
            return "<em>Not available</em>"
        return value

    def _build_briefing_html(self, briefing: BriefingRecord) -> str:
        f = self._field
        return f"""
        <html><body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <h2 style="color: #2c3e50;">{briefing.source_regulator}: {briefing.issuance_title}</h2>
            <p><strong>Issuance:</strong> {briefing.issuance_identifier}</p>
            <p><strong>Executive Summary:</strong> {f(briefing.executive_summary)}</p>
            <p><strong>Impact to MIGI/MILI:</strong> {f(briefing.insurance_entity_impact)}</p>
            <p><strong>Impact to MIBI:</strong> {f(briefing.brokerage_entity_impact)}</p>
            <p><strong>Risk/Priority Level:</strong> {f(briefing.risk_priority_level)}</p>
            <p><strong>Suggested Action:</strong> {f(briefing.suggested_action)}</p>
            <p><strong>Archived Copy:</strong> {f(briefing.archived_document_link)}</p>
            <p><strong>Official Source:</strong> <a href="{briefing.official_source_link}">{briefing.official_source_link}</a></p>
            <p style="font-size: 12px; color: #7f8c8d;">
                Completeness: {briefing.completeness_status}. This is an automated
                notification from the Regulatory Scraper.
            </p>
        </body></html>
        """
