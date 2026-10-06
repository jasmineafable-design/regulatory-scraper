from unittest.mock import MagicMock, patch

import requests

from core.archive import (
    ATTACHED_LABEL,
    MAX_ATTACHMENT_BYTES,
    Archiver,
    ArchiveResult,
    _safe_filename,
)
from core.exceptions import AdapterFetchError
from models.issuance import CandidateIssuance


def _candidate(source_regulator="BIR", source_url="https://www.bir.gov.ph/test.pdf"):
    return CandidateIssuance(
        source_regulator=source_regulator,
        source_category="RMC",
        issuance_identifier="RMC No. 61-2026",
        issuance_title="RMC No. 61-2026 - Test circular",
        source_url=source_url,
        raw_content_reference="raw",
    )


def test_archive_fails_open_on_document_fetch_error():
    archiver = Archiver()

    with patch.object(
        archiver.http_client, "fetch_bytes", side_effect=requests.exceptions.ConnectionError("boom")
    ):
        result = archiver.archive(_candidate())

    assert isinstance(result, ArchiveResult)
    assert result.succeeded is False
    assert "ConnectionError" in result.error
    assert "boom" in result.error
    assert result.archived_document_link == "UNAVAILABLE"
    assert result.attachment_bytes is None


def test_archive_fails_open_on_document_fetch_403_via_proxy_error():
    """The actual production failure (2026-09-28): IC/SEC document URLs are
    blocked from GitHub Actions' IP ranges exactly like their listing pages
    -- fetch_bytes surfaces that as an AdapterFetchError (raised by
    core/http_client.py after exhausting retries), which Archive must fail
    open on same as any other error."""
    archiver = Archiver()

    with patch.object(
        archiver.http_client,
        "fetch_bytes",
        side_effect=AdapterFetchError(
            regulator_id="IC", url="https://www.insurance.gov.ph/some-advisory/",
            original_error=requests.exceptions.HTTPError("403 Client Error: Forbidden"),
        ),
    ):
        result = archiver.archive(_candidate(source_regulator="IC", source_url="https://www.insurance.gov.ph/some-advisory/"))

    assert result.succeeded is False
    assert "403" in result.error


def test_archive_routes_ic_and_sec_documents_through_the_proxy():
    """Fix for the 2026-09-28 incident: every IC/SEC archive attempt 403'd
    because the document fetch bypassed the scraping proxy entirely. IC/SEC
    document fetches must request use_proxy=True, same as their listing
    pages (core/adapters/ic_adapter.py, sec_adapter.py)."""
    for regulator, url in [
        ("IC", "https://www.insurance.gov.ph/some-advisory/"),
        ("SEC", "https://www.sec.gov.ph/opinion-2026/opinion-no-26-01/"),
    ]:
        archiver = Archiver()
        with patch.object(
            archiver.http_client, "fetch_bytes", return_value=(b"%PDF-data", "application/pdf")
        ) as mock_fetch_bytes:
            result = archiver.archive(_candidate(source_regulator=regulator, source_url=url))

        assert result.succeeded is True
        assert mock_fetch_bytes.call_args.kwargs["use_proxy"] is True


def test_archive_does_not_use_proxy_for_bir():
    """BIR isn't proxy-gated (confirmed live 2026-09-28: no BIR archive
    failures occurred, unlike every IC/SEC one) -- its documents should be
    fetched directly, not burn ScraperAPI credit unnecessarily."""
    archiver = Archiver()

    with patch.object(
        archiver.http_client, "fetch_bytes", return_value=(b"%PDF-data", "application/pdf")
    ) as mock_fetch_bytes:
        result = archiver.archive(_candidate(source_regulator="BIR"))

    assert result.succeeded is True
    assert mock_fetch_bytes.call_args.kwargs["use_proxy"] is False


def test_archive_succeeds_and_returns_attachment():
    archiver = Archiver()

    with patch.object(
        archiver.http_client, "fetch_bytes", return_value=(b"%PDF-data", "application/pdf; charset=binary")
    ):
        result = archiver.archive(_candidate())

    assert result.succeeded is True
    assert result.archived_document_link == ATTACHED_LABEL
    assert result.attachment_bytes == b"%PDF-data"
    assert result.attachment_content_type == "application/pdf"
    assert result.attachment_filename.endswith(".pdf")
    assert result.attachment_filename == "BIR_RMC_RMC-No-61-2026.pdf"


def test_archive_fails_open_when_document_is_empty():
    archiver = Archiver()

    with patch.object(archiver.http_client, "fetch_bytes", return_value=(b"", "application/pdf")):
        result = archiver.archive(_candidate())

    assert result.succeeded is False
    assert "empty" in result.error.lower()


def test_archive_fails_open_when_document_too_large_to_attach():
    archiver = Archiver()
    big = b"x" * (MAX_ATTACHMENT_BYTES + 1)

    with patch.object(archiver.http_client, "fetch_bytes", return_value=(big, "application/pdf")):
        result = archiver.archive(_candidate())

    assert result.succeeded is False
    assert "limit" in result.error
    assert result.attachment_bytes is None


# --- Drive-link tier (Apps Script web app), 2026-10-07 ---------------------


def _drive_archiver():
    return Archiver(upload_url="https://script.google.com/macros/s/ABC/exec", upload_token="s3cret")


def _post_response(json_body=None, json_error=False, status_error=None):
    resp = MagicMock()
    if status_error:
        resp.raise_for_status.side_effect = status_error
    else:
        resp.raise_for_status.return_value = None
    if json_error:
        resp.json.side_effect = ValueError("not json")
    else:
        resp.json.return_value = json_body
    return resp


def test_archive_uploads_to_drive_and_returns_the_link_when_configured():
    archiver = _drive_archiver()
    drive_link = "https://drive.google.com/file/d/xyz/view"

    with patch.object(archiver.http_client, "fetch_bytes", return_value=(b"%PDF-data", "application/pdf")), \
         patch("core.archive.requests.post", return_value=_post_response({"ok": True, "url": drive_link})) as post:
        result = archiver.archive(_candidate())

    assert result.succeeded is True
    assert result.archived_document_link == drive_link
    assert result.attachment_bytes is None            # link replaces the attachment
    sent = post.call_args.kwargs["json"]
    assert sent["token"] == "s3cret"
    assert sent["filename"] == "BIR_RMC_RMC-No-61-2026.pdf"
    assert sent["content_type"] == "application/pdf"
    assert sent["data"]                               # base64 document


def test_archive_falls_back_to_attachment_when_drive_upload_fails():
    for post_response in [
        _post_response({"ok": False, "error": "bad token"}),
        _post_response(json_error=True),                                        # HTML sign-in page, not JSON
        _post_response(status_error=requests.exceptions.HTTPError("500 boom")),
        _post_response({"ok": True, "url": ""}),
    ]:
        archiver = _drive_archiver()
        with patch.object(archiver.http_client, "fetch_bytes", return_value=(b"%PDF-data", "application/pdf")), \
             patch("core.archive.requests.post", return_value=post_response):
            result = archiver.archive(_candidate())

        assert result.succeeded is True
        assert result.archived_document_link == ATTACHED_LABEL
        assert result.attachment_bytes == b"%PDF-data"


def test_archive_falls_back_to_attachment_when_drive_endpoint_unreachable():
    archiver = _drive_archiver()
    with patch.object(archiver.http_client, "fetch_bytes", return_value=(b"%PDF-data", "application/pdf")), \
         patch("core.archive.requests.post", side_effect=requests.exceptions.ConnectionError("down")):
        result = archiver.archive(_candidate())

    assert result.succeeded is True
    assert result.attachment_bytes == b"%PDF-data"


def test_archive_does_not_call_drive_when_not_configured(monkeypatch):
    monkeypatch.delenv("DRIVE_UPLOAD_URL", raising=False)
    monkeypatch.delenv("DRIVE_UPLOAD_TOKEN", raising=False)
    archiver = Archiver()

    with patch.object(archiver.http_client, "fetch_bytes", return_value=(b"%PDF-data", "application/pdf")), \
         patch("core.archive.requests.post") as post:
        result = archiver.archive(_candidate())

    post.assert_not_called()
    assert result.attachment_bytes == b"%PDF-data"


def test_safe_filename_sanitizes_and_adds_extension():
    name = _safe_filename(_candidate(), "application/pdf")

    assert name == "BIR_RMC_RMC-No-61-2026.pdf"


def test_safe_filename_strips_regulator_prefix_from_type():
    ic = CandidateIssuance(
        source_regulator="IC", source_category="IC-CL", issuance_identifier="CL 2026-05",
        issuance_title="t", source_url="u", raw_content_reference="r",
    )
    sec = CandidateIssuance(
        source_regulator="SEC", source_category="SEC-RESOLUTION", issuance_identifier="Res. No. 12 s.2026",
        issuance_title="t", source_url="u", raw_content_reference="r",
    )

    assert _safe_filename(ic, "application/pdf") == "IC_CL_CL-2026-05.pdf"
    assert _safe_filename(sec, None) == "SEC_RESOLUTION_Res-No-12-s-2026"


def test_safe_filename_always_splits_into_three_parts():
    """The Drive-copy script splits on '_' (max 2 splits) to find
    regulator/type -- no part may itself contain an underscore."""
    for regulator, category, identifier in [
        ("BIR", "RMC", "RMC No. 1_2-2026"),
        ("IC", "IC-ADVISORY", "RS_2026_008"),
        ("SEC", "SEC-MC", "MC No. 5 s.2026"),
    ]:
        c = CandidateIssuance(
            source_regulator=regulator, source_category=category, issuance_identifier=identifier,
            issuance_title="t", source_url="u", raw_content_reference="r",
        )
        stem = _safe_filename(c, "application/pdf").rsplit(".", 1)[0]
        parts = stem.split("_", 2)
        assert len(parts) == 3
        assert parts[0] == regulator
        assert "_" not in parts[1]


def test_safe_filename_has_no_extension_for_unknown_content_type():
    # An unrecognized content type shouldn't have any extension guessed/
    # appended -- same result as passing no content type at all.
    name_unknown = _safe_filename(_candidate(), "application/x-totally-unknown")
    name_none = _safe_filename(_candidate(), None)

    assert name_unknown == name_none
