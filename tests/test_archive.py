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
    big = b"%PDF" + b"x" * MAX_ATTACHMENT_BYTES   # a real-looking PDF, just too big

    with patch.object(archiver.http_client, "fetch_bytes", return_value=(big, "application/pdf")):
        result = archiver.archive(_candidate())

    assert result.succeeded is False
    assert "limit" in result.error
    assert result.attachment_bytes is None


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


# --- IC/SEC: follow the page's PDF link (confirmed live 2026-10-07) --------

SEC_PAGE = b"""<html><body>
<nav><a href="/wp-content/uploads/2020/citizens-charter.pdf">Citizen's Charter</a></nav>
<article><div class="entry-content">
  <a href="https://www.sec.gov.ph/wp-content/uploads/2026/10/2026MC_SEC-MC-No.-27.pdf">Download to View File</a>
</div></article></body></html>"""

IC_PAGE = b"""<html><body><article>
  <iframe src="https://www.insurance.gov.ph/wp-content/uploads/2026/07/IC-CL-2026-14.pdf#toolbar=0"></iframe>
  <a href="/wp-content/uploads/2026/07/IC-CL-2026-14.pdf">Download</a>
</article></body></html>"""


def test_sec_page_is_followed_to_its_pdf_not_the_site_menu_pdf():
    archiver = Archiver()
    pages = {
        "https://www.sec.gov.ph/mc-2026/sec-mc-no-27/": (SEC_PAGE, "text/html; charset=UTF-8"),
        "https://www.sec.gov.ph/wp-content/uploads/2026/10/2026MC_SEC-MC-No.-27.pdf": (b"%PDF-1.7 real", "application/pdf"),
    }
    fetch = MagicMock(side_effect=lambda reg, url, use_proxy=False: pages[url])

    with patch.object(archiver.http_client, "fetch_bytes", fetch):
        result = archiver.archive(_candidate("SEC", "https://www.sec.gov.ph/mc-2026/sec-mc-no-27/"))

    assert result.succeeded is True
    assert result.attachment_bytes == b"%PDF-1.7 real"
    assert result.attachment_filename.endswith(".pdf")
    assert fetch.call_count == 2
    assert all(call.kwargs["use_proxy"] is True for call in fetch.call_args_list)   # SEC is proxy-gated


def test_ic_page_with_embedded_pdf_is_followed_and_relative_links_resolve():
    archiver = Archiver()
    page_url = "https://www.insurance.gov.ph/circular-letter-no-2026-14/"
    pdf_url = "https://www.insurance.gov.ph/wp-content/uploads/2026/07/IC-CL-2026-14.pdf"
    pages = {page_url: (IC_PAGE, "text/html"), pdf_url: (b"%PDF-1.7 ic", "application/pdf")}
    fetch = MagicMock(side_effect=lambda reg, url, use_proxy=False: pages[url])

    with patch.object(archiver.http_client, "fetch_bytes", fetch):
        result = archiver.archive(_candidate("IC", page_url))

    assert result.attachment_bytes == b"%PDF-1.7 ic"
    assert fetch.call_args_list[1].args[1] == pdf_url


def test_direct_pdf_urls_are_not_fetched_twice():
    """BIR links straight to the PDF -- one fetch, as before."""
    archiver = Archiver()
    fetch = MagicMock(return_value=(b"%PDF-1.4 bir", "application/pdf"))

    with patch.object(archiver.http_client, "fetch_bytes", fetch):
        result = archiver.archive(_candidate("BIR"))

    assert fetch.call_count == 1
    assert result.attachment_bytes == b"%PDF-1.4 bir"


def test_page_without_a_pdf_link_is_not_attached_and_flags_unavailable():
    """Gmail blocked a whole briefing that carried saved web pages, so a page
    is never attached: the archive field is flagged instead."""
    archiver = Archiver()
    page = b"<html><body><article><p>No file here</p></article></body></html>"

    with patch.object(archiver.http_client, "fetch_bytes", return_value=(page, "text/html")) as fetch:
        result = archiver.archive(_candidate("IC", "https://www.insurance.gov.ph/x/"))

    assert fetch.call_count == 1
    assert result.succeeded is False
    assert result.attachment_bytes is None
    assert result.archived_document_link == "UNAVAILABLE"
    assert "not attaching the web page" in result.error


def test_page_is_not_attached_when_fetching_its_pdf_fails():
    archiver = Archiver()
    calls = {"n": 0}

    def fetch(reg, url, use_proxy=False):
        calls["n"] += 1
        if calls["n"] == 1:
            return SEC_PAGE, "text/html"
        raise requests.exceptions.ConnectionError("pdf host down")

    with patch.object(archiver.http_client, "fetch_bytes", side_effect=fetch):
        result = archiver.archive(_candidate("SEC", "https://www.sec.gov.ph/mc-2026/sec-mc-no-27/"))

    assert result.succeeded is False
    assert result.attachment_bytes is None


def test_challenge_page_served_as_a_pdf_is_rejected():
    """A proxy/Cloudflare block page must never be attached as if it were the PDF."""
    archiver = Archiver()
    block_page = b"Just a moment... please enable cookies"

    with patch.object(archiver.http_client, "fetch_bytes", return_value=(block_page, "application/pdf")):
        result = archiver.archive(_candidate("BIR"))

    assert result.succeeded is False
    assert "not a valid PDF" in result.error
