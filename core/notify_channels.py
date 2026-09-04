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

    def send_regulatory_briefing_digest(self, briefings: List[BriefingRecord]) -> List[BriefingRecord]:
        """Sends one table-format digest email per distinct recipient audience,
        covering every new issuance found in this run (§3.7 still applies --
        "send immediately whenever anything new is found on any check, opening
        or recurring" -- this only changes *how many issuances share one email*,
        not *when* an email goes out).

        Reverted to this table-digest format (was one plain field-list email
        per issuance) on 2026-09-03 per Jas's explicit preference for the
        original table style. Recipients still route per (regulator, category)
        via `_recipients_for` -- a run touching multiple audiences sends one
        digest per audience, not one email covering everyone.

        Returns the subset of `briefings` whose digest email sent successfully,
        so the caller (NotificationDispatcher) only commits state for briefings
        that were actually delivered.
        """
        if not briefings:
            return []

        groups: Dict[Tuple[str, ...], Tuple[List[str], List[BriefingRecord]]] = {}
        for briefing in briefings:
            recipients = self._recipients_for(briefing.source_regulator, briefing.source_category)
            key = tuple(sorted(recipients))
            if key not in groups:
                groups[key] = (recipients, [])
            groups[key][1].append(briefing)

        successful: List[BriefingRecord] = []
        for recipients, group_briefings in groups.values():
            subject = self._digest_subject(group_briefings)
            html_body = self._build_digest_html(group_briefings)
            if self._send(subject, html_body, recipients):
                successful.extend(group_briefings)
            else:
                logger.error(
                    "Failed to dispatch digest covering "
                    f"{[b.issuance_identifier for b in group_briefings]}"
                )
        return successful

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

    @staticmethod
    def _digest_subject(briefings: List[BriefingRecord]) -> str:
        regulators = sorted({b.source_regulator for b in briefings})
        return f"[Regulatory Briefing] {', '.join(regulators)}: {len(briefings)} new issuance(s)"

    def _build_digest_html(self, briefings: List[BriefingRecord]) -> str:
        f = self._field

        counts: Dict[str, int] = {}
        for b in briefings:
            counts[b.source_category] = counts.get(b.source_category, 0) + 1
        counts_line = " | ".join(f"{n} {cat}" for cat, n in sorted(counts.items()))

        # Column labels renamed 2026-09-04 per Jas: entity codes (MIGI/MILI/
        # MIBI) replaced with plain-language roles, so recipients who don't
        # know the internal abbreviations can read the digest. The underlying
        # BriefingRecord field names are unchanged -- insurance_entity_impact
        # is still MIGI/MILI (the underwriters) and brokerage_entity_impact is
        # still MIBI (the brokerage); only the display label differs.
        # Explicit widths, 2026-09-04 per Jas ("columns are not equally
        # distributed... long paragraphs like impact have small column").
        #
        # First attempt used a <colgroup>/<col> to set these -- that's
        # ignored by Gmail and most other webmail clients (a well-known HTML
        # email limitation, colgroup support is inconsistent), so it silently
        # fell back to auto-sizing by content and every column ended up
        # roughly the same width regardless of what was declared. Fixed by
        # putting the width directly on each <th>/<td> instead, which is the
        # standard, broadly-supported technique for HTML email tables. Also
        # set as both a `width` HTML attribute and an inline style -- older
        # Outlook builds honor the attribute more reliably than the CSS.
        # These widths add up to 100% and deliberately favor the paragraph
        # columns (Executive Summary, the two Impact columns, Suggested
        # Action) over the short ones (Issuance, Risk, Archived Copy).
        COLUMN_WIDTHS = [10, 20, 15, 15, 8, 17, 7, 8]  # must sum to 100

        header_labels = [
            "Issuance", "Executive Summary", "Impact to Underwriting Entities",
            "Impact to Broker Entity", "Risk/Priority Level", "Suggested Action",
            "Archived Copy", "Official Source",
        ]
        # text-align: center on headers per Jas, 2026-09-04. Body cells stay
        # left-aligned -- centring paragraph-length summaries makes them much
        # harder to read.
        header_html = "".join(
            f'<th width="{w}%" style="width: {w}%; padding: 8px 12px; border: 1px solid #dfe3e6; '
            f'background-color: #2c3e50; color: #fff; text-align: center;">{label}</th>'
            for label, w in zip(header_labels, COLUMN_WIDTHS)
        )
        w_issuance, w_summary, w_underwriting, w_broker, w_risk, w_action, w_archive, w_source = COLUMN_WIDTHS

        row_html = "\n".join(
            f"""
                <tr>
                    <td width="{w_issuance}%" style="width: {w_issuance}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top; word-break: break-word;">
                        <strong>{b.issuance_identifier}</strong><br/>
                        <span style="font-size: 12px; color: #7f8c8d;">{b.source_regulator} / {b.source_category}</span>
                    </td>
                    <td width="{w_summary}%" style="width: {w_summary}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top;">{f(b.executive_summary)}</td>
                    <td width="{w_underwriting}%" style="width: {w_underwriting}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top;">{f(b.insurance_entity_impact)}</td>
                    <td width="{w_broker}%" style="width: {w_broker}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top;">{f(b.brokerage_entity_impact)}</td>
                    <td width="{w_risk}%" style="width: {w_risk}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top;">{f(b.risk_priority_level)}</td>
                    <td width="{w_action}%" style="width: {w_action}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top;">{f(b.suggested_action)}</td>
                    <td width="{w_archive}%" style="width: {w_archive}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top;">{f(b.archived_document_link)}</td>
                    <td width="{w_source}%" style="width: {w_source}%; padding: 8px 12px; border: 1px solid #dfe3e6; vertical-align: top; word-break: break-all;">
                        <a href="{b.official_source_link}">View source</a>
                    </td>
                </tr>"""
            for b in briefings
        )

        any_degraded = any(b.completeness_status != "complete" for b in briefings)
        degraded_note = (
            'Some items above have incomplete AI-assessed fields (marked "Not available"). '
            if any_degraded else ""
        )

        return f"""
        <html><body style="font-family: Arial, sans-serif; color: #333; line-height: 1.6;">
            <h2 style="color: #2c3e50;">New Regulatory Updates</h2>
            <p style="background-color: #f7f9fa; padding: 8px 12px; border-radius: 4px; display: inline-block;">
                New this check: {counts_line} | <strong>{len(briefings)} total</strong>
            </p>
            <table style="border-collapse: collapse; width: 100%; table-layout: fixed;">
                <tr>{header_html}</tr>
                {row_html}
            </table>
            <p style="font-size: 12px; color: #7f8c8d;">
                {degraded_note}This is an automated notification from the Regulatory Scraper.
            </p>
        </body></html>
        """
