import email
import re
from unittest.mock import MagicMock, patch

from core.notify_channels import EmailNotificationChannel
from models.issuance import BriefingRecord


def _briefing(regulator="BIR", category="RMC", identifier="RMC No. 1-2026", **overrides) -> BriefingRecord:
    defaults = dict(
        issuance_identifier=identifier,
        source_regulator=regulator,
        source_category=category,
        issuance_title=f"{identifier} - Test issuance",
        official_source_link="https://www.bir.gov.ph/test",
    )
    defaults.update(overrides)
    return BriefingRecord(**defaults)


def test_digest_builds_one_table_row_per_briefing():
    channel = EmailNotificationChannel(default_recipients=["ops@x.com"])
    briefings = [
        _briefing(identifier="RMC No. 1-2026", executive_summary="Summary one."),
        _briefing(identifier="RMC No. 2-2026", executive_summary="Summary two."),
    ]

    html = channel._build_digest_html(briefings)

    assert html.count("<table") == 1
    assert "RMC No. 1-2026" in html
    assert "RMC No. 2-2026" in html
    assert "Summary one." in html
    assert "Summary two." in html
    assert "2 total" in html


def test_digest_shows_not_available_for_unavailable_fields():
    channel = EmailNotificationChannel(default_recipients=["ops@x.com"])
    briefing = _briefing(executive_summary="UNAVAILABLE", completeness_status="degraded")

    html = channel._build_digest_html([briefing])

    assert "<em>Not available</em>" in html
    assert "incomplete AI-assessed fields" in html


def test_digest_sends_one_email_per_distinct_recipient_group():
    channel = EmailNotificationChannel(
        recipient_matrix={
            ("BIR", "RMC"): ["tax@x.com"],
            ("IC", "IC-CL"): ["legal@x.com"],
        },
        default_recipients=["fallback@x.com"],
    )
    briefings = [
        _briefing(regulator="BIR", category="RMC", identifier="RMC No. 1-2026"),
        _briefing(regulator="BIR", category="RMC", identifier="RMC No. 2-2026"),
        _briefing(regulator="IC", category="IC-CL", identifier="CL-2026-005"),
    ]

    with patch.object(channel, "_send", return_value=True) as mock_send:
        successful = channel.send_regulatory_briefing_digest(briefings)

    assert len(successful) == 3
    assert mock_send.call_count == 2  # one email per distinct recipient group
    sent_recipient_lists = [call.args[2] for call in mock_send.call_args_list]
    assert ["tax@x.com"] in sent_recipient_lists
    assert ["legal@x.com"] in sent_recipient_lists


def test_digest_only_reports_success_for_groups_that_actually_sent():
    channel = EmailNotificationChannel(
        recipient_matrix={
            ("BIR", "RMC"): ["tax@x.com"],
            ("IC", "IC-CL"): ["legal@x.com"],
        },
    )
    ok_briefing = _briefing(regulator="BIR", category="RMC", identifier="RMC No. 1-2026")
    failing_briefing = _briefing(regulator="IC", category="IC-CL", identifier="CL-2026-005")

    def fake_send(subject, html_body, recipients, attachments=None):
        return recipients == ["tax@x.com"]

    with patch.object(channel, "_send", side_effect=fake_send):
        successful = channel.send_regulatory_briefing_digest([ok_briefing, failing_briefing])

    assert successful == [ok_briefing]


def test_exact_regulator_category_match_wins():
    channel = EmailNotificationChannel(
        recipient_matrix={
            ("IC", "IC-CL"): ["compliance@x.com"],
            ("IC", "IC-ADVISORY"): ["legal@x.com"],
        },
        default_recipients=["fallback@x.com"],
    )
    assert channel._recipients_for("IC", "IC-CL") == ["compliance@x.com"]
    assert channel._recipients_for("IC", "IC-ADVISORY") == ["legal@x.com"]


def test_falls_back_to_regulator_wide_when_category_unmatched():
    channel = EmailNotificationChannel(
        recipient_matrix={("BIR", "RMC"): ["tax@x.com"]},
        default_recipients=["fallback@x.com"],
    )
    # Same regulator, a category with no specific mapping -> regulator-wide recipients.
    assert channel._recipients_for("BIR", "RR") == ["tax@x.com"]


def test_falls_back_to_default_when_regulator_unmatched():
    channel = EmailNotificationChannel(
        recipient_matrix={("BIR", "RMC"): ["tax@x.com"]},
        default_recipients=["fallback@x.com"],
    )
    assert channel._recipients_for("SEC", "SEC-MC") == ["fallback@x.com"]


# --- Attachment tests, 2026-10-06 (archive = email attachment) ------------


def _with_doc(identifier="RMC No. 1-2026", size=10, name=None, **overrides):
    return _briefing(
        identifier=identifier,
        archived_document_link="Attached to this email",
        attachment_filename=name or f"{identifier.replace(' ', '_')}.pdf",
        attachment_content_type="application/pdf",
        attachment_bytes=b"%" * size,
        **overrides,
    )


def _sent_message(channel, briefings):
    """Runs the real digest send with SMTP mocked, returns the parsed email."""
    channel.sender_email = "bot@x.com"
    channel.sender_password = "pw"
    smtp = MagicMock()
    with patch("core.notify_channels.smtplib.SMTP") as smtp_cls:
        smtp_cls.return_value.__enter__.return_value = smtp
        channel.send_regulatory_briefing_digest(briefings)
    raw = smtp.sendmail.call_args.args[2]
    return email.message_from_string(raw)


def test_digest_email_carries_documents_as_attachments():
    channel = EmailNotificationChannel(default_recipients=["ops@x.com"])
    msg = _sent_message(channel, [_with_doc("RMC No. 1-2026"), _with_doc("RMC No. 2-2026")])

    assert msg.get_content_type() == "multipart/mixed"
    names = [p.get_filename() for p in msg.walk() if p.get_filename()]
    assert names == ["RMC_No._1-2026.pdf", "RMC_No._2-2026.pdf"]
    body = next(p for p in msg.walk() if p.get_content_type() == "text/html")
    assert "Attached" in body.get_payload(decode=True).decode()


def test_digest_email_without_documents_stays_plain():
    channel = EmailNotificationChannel(default_recipients=["ops@x.com"])
    msg = _sent_message(channel, [_briefing()])

    assert msg.get_content_type() == "multipart/alternative"
    assert not [p for p in msg.walk() if p.get_filename()]


def test_drive_link_renders_as_a_clickable_link_not_raw_text():
    channel = EmailNotificationChannel(default_recipients=["ops@x.com"])
    link = "https://drive.google.com/file/d/abc/view?usp=drivesdk&x=1"
    html_out = channel._build_digest_html([_briefing(archived_document_link=link, completeness_status="complete")])

    assert 'href="https://drive.google.com/file/d/abc/view?usp=drivesdk&amp;x=1">Open in Drive</a>' in html_out
    assert "Attached" not in html_out


def test_duplicate_attachment_filenames_are_made_unique():
    channel = EmailNotificationChannel(default_recipients=["ops@x.com"])
    briefings = [
        _with_doc("RMC No. 1-2026", name="same.pdf"),
        _with_doc("RMC No. 2-2026", name="same.pdf"),
    ]

    attachments, not_attached = channel._collect_attachments(briefings)

    assert [a[0] for a in attachments] == ["same.pdf", "same_2.pdf"]
    assert not_attached == set()


def test_documents_past_total_size_cap_are_left_off_and_flagged():
    channel = EmailNotificationChannel(default_recipients=["ops@x.com"])
    half = channel.MAX_TOTAL_ATTACHMENT_BYTES // 2 + 1
    briefings = [
        _with_doc("RMC No. 1-2026", size=half),
        _with_doc("RMC No. 2-2026", size=half),  # would push total over the cap
    ]

    attachments, not_attached = channel._collect_attachments(briefings)
    html_out = channel._build_digest_html(briefings, not_attached_ids=not_attached)

    assert len(attachments) == 1
    assert not_attached == {"RMC No. 2-2026"}
    assert "Too large to attach" in html_out


# --- Regression tests, 2026-09-04 table-width review ---------------------


def test_digest_columns_have_explicit_widths_summing_to_100():
    """Jas: 'columns are not equally distributed... long paragraphs like
    impact have small column.' First fix used a <colgroup>, which Gmail (and
    most webmail) silently ignores, so every column still ended up roughly
    equal regardless of the declared %. Widths must be set on each <th>/<td>
    directly, and must sum to 100 or the table overflows/underfills."""
    channel = EmailNotificationChannel(default_recipients=["x@y.z"])
    briefing = _briefing(executive_summary="A summary.")
    html = channel._build_digest_html([briefing])

    assert "<colgroup>" not in html, "colgroup widths are silently dropped by Gmail -- don't reintroduce"

    header_widths = [int(w) for w in re.findall(r'<th width="(\d+)%"', html)]
    row_widths = [int(w) for w in re.findall(r'<td width="(\d+)%"', html)]
    assert len(header_widths) == 8
    assert sum(header_widths) == 100
    assert row_widths == header_widths, "each row's cell widths must match the header's"
    assert "table-layout: fixed" in html


def test_official_source_link_text_is_short_not_the_raw_url():
    """A long raw URL as link text was itself forcing that column wide."""
    channel = EmailNotificationChannel(default_recipients=["x@y.z"])
    long_url = "https://www.insurance.gov.ph/some/very/long/path/to/document.pdf"
    briefing = _briefing(official_source_link=long_url)
    html = channel._build_digest_html([briefing])

    assert f'href="{long_url}">View source</a>' in html
    assert long_url not in html.split("View source")[0].rsplit("href=", 1)[-1][: len(long_url) - 5]


# --- Archive folder link in every email, 2026-10-07 ----------------------


def test_emails_link_to_the_archive_folder_when_configured(monkeypatch):
    monkeypatch.setenv("ARCHIVE_FOLDER_URL", "https://drive.google.com/drive/folders/ABC123")
    channel = EmailNotificationChannel(default_recipients=["x@y.z"])

    digest = channel._build_digest_html([_briefing()])
    assert 'href="https://drive.google.com/drive/folders/ABC123">Open the Regulatory Archive</a>' in digest

    sent = {}
    channel.sender_email, channel.sender_password = "bot@x.com", "pw"
    with patch.object(channel, "_send", side_effect=lambda s, body, r, attachments=None: sent.update(body=body) or True):
        channel.send_daily_monitoring_report("opening check")
    assert "Open the Regulatory Archive" in sent["body"]


def test_no_archive_line_when_url_unset_or_not_https(monkeypatch):
    for value in ["", "http://insecure.example/folder", "javascript:alert(1)"]:
        monkeypatch.setenv("ARCHIVE_FOLDER_URL", value)
        channel = EmailNotificationChannel(default_recipients=["x@y.z"])
        assert "Regulatory Archive" not in channel._build_digest_html([_briefing()])
