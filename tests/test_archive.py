from unittest.mock import MagicMock, patch

import requests

from core.archive import Archiver, ArchiveResult, _safe_filename
from models.issuance import CandidateIssuance


def _candidate():
    return CandidateIssuance(
        source_regulator="BIR",
        source_category="RMC",
        issuance_identifier="RMC No. 61-2026",
        issuance_title="RMC No. 61-2026 - Test circular",
        source_url="https://www.bir.gov.ph/test.pdf",
        raw_content_reference="raw",
    )


def _fake_response(json_data=None, content=b"", headers=None, raise_for_status_error=None):
    resp = MagicMock()
    resp.headers = headers or {}
    resp.content = content
    if raise_for_status_error:
        resp.raise_for_status.side_effect = raise_for_status_error
    else:
        resp.raise_for_status.return_value = None
    if json_data is not None:
        resp.json.return_value = json_data
    return resp


def test_archive_fails_open_when_config_missing(monkeypatch):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.delenv("DRIVE_FOLDER_ID", raising=False)
    archiver = Archiver()

    result = archiver.archive(_candidate())

    assert isinstance(result, ArchiveResult)
    assert result.succeeded is False
    assert result.archived_document_link == "UNAVAILABLE"
    assert "GOOGLE_SERVICE_ACCOUNT_JSON" in result.error
    assert "DRIVE_FOLDER_ID" in result.error


def test_archive_fails_open_when_only_folder_id_missing(monkeypatch):
    archiver = Archiver(service_account_json="{}", folder_id=None)
    monkeypatch.delenv("DRIVE_FOLDER_ID", raising=False)

    result = archiver.archive(_candidate())

    assert result.succeeded is False


def test_archive_fails_open_on_document_fetch_error():
    archiver = Archiver(service_account_json="{}", folder_id="folder123")

    with patch("core.archive.requests.get", side_effect=requests.exceptions.ConnectionError("boom")):
        result = archiver.archive(_candidate())

    assert result.succeeded is False
    assert "ConnectionError" in result.error
    assert "boom" in result.error
    assert result.archived_document_link == "UNAVAILABLE"


def test_archive_fails_open_on_upload_error():
    archiver = Archiver(service_account_json="{}", folder_id="folder123")
    archiver._session = MagicMock()
    archiver._session.post.side_effect = requests.exceptions.HTTPError("upload failed")

    doc_response = _fake_response(content=b"%PDF-data", headers={"Content-Type": "application/pdf"})

    with patch("core.archive.requests.get", return_value=doc_response):
        result = archiver.archive(_candidate())

    assert result.succeeded is False
    assert "upload failed" in result.error


def test_archive_fails_open_on_permission_error():
    archiver = Archiver(service_account_json="{}", folder_id="folder123")
    upload_response = _fake_response(json_data={"id": "file123", "webViewLink": "https://drive.google.com/file/d/file123/view"})
    permission_response = _fake_response(raise_for_status_error=requests.exceptions.HTTPError("perm failed"))
    archiver._session = MagicMock()
    archiver._session.post.side_effect = [upload_response, permission_response]

    doc_response = _fake_response(content=b"%PDF-data", headers={"Content-Type": "application/pdf"})

    with patch("core.archive.requests.get", return_value=doc_response):
        result = archiver.archive(_candidate())

    assert result.succeeded is False
    assert "perm failed" in result.error


def test_archive_succeeds_and_returns_drive_link():
    archiver = Archiver(service_account_json="{}", folder_id="folder123")
    upload_response = _fake_response(json_data={"id": "file123", "webViewLink": "https://drive.google.com/file/d/file123/view"})
    permission_response = _fake_response()
    archiver._session = MagicMock()
    archiver._session.post.side_effect = [upload_response, permission_response]

    doc_response = _fake_response(content=b"%PDF-data", headers={"Content-Type": "application/pdf"})

    with patch("core.archive.requests.get", return_value=doc_response):
        result = archiver.archive(_candidate())

    assert result.succeeded is True
    assert result.archived_document_link == "https://drive.google.com/file/d/file123/view"

    # Uploaded into the configured folder, and made link-viewable (per Jas,
    # 2026-09-28: recipients are arbitrary business emails, not all in one
    # Workspace domain).
    upload_call = archiver._session.post.call_args_list[0]
    assert upload_call.kwargs["files"]["metadata"][1].count("folder123") == 1

    permission_call = archiver._session.post.call_args_list[1]
    assert permission_call.kwargs["json"] == {"role": "reader", "type": "anyone"}


def test_archive_falls_back_to_view_url_if_webviewlink_missing():
    archiver = Archiver(service_account_json="{}", folder_id="folder123")
    upload_response = _fake_response(json_data={"id": "file123"})  # no webViewLink
    permission_response = _fake_response()
    archiver._session = MagicMock()
    archiver._session.post.side_effect = [upload_response, permission_response]

    doc_response = _fake_response(content=b"%PDF-data", headers={"Content-Type": "application/pdf"})

    with patch("core.archive.requests.get", return_value=doc_response):
        result = archiver.archive(_candidate())

    assert result.succeeded is True
    assert result.archived_document_link == "https://drive.google.com/file/d/file123/view"


def test_safe_filename_sanitizes_and_adds_extension():
    name = _safe_filename(_candidate(), "application/pdf")

    assert name.endswith(".pdf")
    assert " " not in name
    assert "BIR-RMC" in name


def test_safe_filename_has_no_extension_for_unknown_content_type():
    # An unrecognized content type shouldn't have any extension guessed/
    # appended -- same result as passing no content type at all.
    name_unknown = _safe_filename(_candidate(), "application/x-totally-unknown")
    name_none = _safe_filename(_candidate(), None)

    assert name_unknown == name_none
