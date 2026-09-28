"""
Archive step (Foundation §3.6/§4.4, Phase 5).

Best-effort document archiving (Foundation §3.9: "Not a full document
management system -- archiving is convenience, not records-management").

Approved best-effort failure behavior (frozen, §3.8, same rule Phase 4/Assess
follows): if this fails for any reason (missing config, network error, Drive
API error), Compose must still produce a Briefing Record from deterministic
data alone, with the missing section explicitly marked -- never silently
incomplete, never withheld. This module enforces that by never raising:
archive() always returns an ArchiveResult, with .succeeded=False and an
.error on any failure.
"""

import json
import logging
import mimetypes
import os
import re
from dataclasses import dataclass
from typing import Optional

import requests

from models.issuance import CandidateIssuance

logger = logging.getLogger(__name__)

DRIVE_UPLOAD_URL = (
    "https://www.googleapis.com/upload/drive/v3/files"
    "?uploadType=multipart&fields=id,webViewLink"
)
DRIVE_PERMISSIONS_URL_TEMPLATE = "https://www.googleapis.com/drive/v3/files/{file_id}/permissions"

# drive.file (not the broader "drive" scope) -- the service account only
# needs to create/manage files it itself creates inside the configured
# folder, not read/write everything in the account's Drive (§3.9: archiving
# is convenience, not a document-management system -- least-privilege access
# matches that framing).
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.file"]

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _describe_exception(err: BaseException, max_depth: int = 4) -> str:
    """Renders an exception together with its underlying cause chain, same
    as core/assess.py's helper of the same name -- a bare str(err) can hide
    the actionable detail in __cause__ (see assess.py's 2026-09-04 incident).
    Duplicated rather than imported to keep this module's only real
    dependencies scoped to what Archive itself needs."""
    parts = []
    seen = set()
    current: Optional[BaseException] = err
    depth = 0
    while current is not None and depth < max_depth and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip() or "(no message)"
        parts.append(f"{type(current).__name__}: {text}")
        current = current.__cause__ or current.__context__
        depth += 1
    return " <- ".join(parts)


def _safe_filename(candidate: CandidateIssuance, content_type: Optional[str]) -> str:
    """Builds a Drive-safe filename from the issuance identifier, with an
    extension guessed from the response's Content-Type (falls back to no
    extension if the type is unrecognized -- Drive still stores/opens the
    file fine without one)."""
    base = f"{candidate.source_regulator}-{candidate.source_category}-{candidate.issuance_identifier}"
    base = _SAFE_NAME_RE.sub("_", base).strip("_")[:150] or "issuance"
    ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) if content_type else None
    return f"{base}{ext or ''}"


@dataclass
class ArchiveResult:
    succeeded: bool
    archived_document_link: str = "UNAVAILABLE"
    error: Optional[str] = None


class Archiver:
    """Best-effort document archiving to Google Drive (Phase 5).

    Reuses the same GOOGLE_SERVICE_ACCOUNT_JSON credential already used for
    Sheets config (core/sheets_config.py), authenticating via google-auth's
    AuthorizedSession and calling the Drive API v3 REST endpoints directly --
    avoids adding google-api-python-client as a new dependency, consistent
    with this codebase's minimal-dependency convention (gspread + google-auth
    are already required for Sheets).

    Gated exactly like SheetsConfigReader: if GOOGLE_SERVICE_ACCOUNT_JSON or
    DRIVE_FOLDER_ID isn't configured, every call returns a documented
    unavailable result rather than raising -- Archive is explicitly
    non-authoritative and best-effort (§3.9), never blocking the briefing.

    Uploaded files are set to "anyone with the link can view" (confirmed with
    Jas 2026-09-28): Sources-sheet recipients are arbitrary business emails,
    not necessarily all in one Google Workspace domain the service account
    could instead share a private folder with, and these are public
    regulator issuances (BIR/IC/SEC), so link-visibility is an acceptable
    trade-off for recipients being able to open the link at all.
    """

    FETCH_TIMEOUT_SEC = 30
    UPLOAD_TIMEOUT_SEC = 60

    def __init__(self, service_account_json: Optional[str] = None, folder_id: Optional[str] = None):
        self.service_account_json = service_account_json or os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
        self.folder_id = folder_id or os.getenv("DRIVE_FOLDER_ID")
        self._session = None

    def _get_session(self):
        if self._session is None:
            from google.auth.transport.requests import AuthorizedSession  # imported lazily: optional dependency
            from google.oauth2 import service_account

            # Same "raw JSON text vs. real file path" detection as
            # SheetsConfigReader.__init__ (core/sheets_config.py) -- the
            # README documents pasting the whole JSON key file contents into
            # the GitHub secret, not a path to a file that doesn't exist on
            # the runner.
            try:
                credentials_dict = json.loads(self.service_account_json)
                credentials = service_account.Credentials.from_service_account_info(
                    credentials_dict, scopes=DRIVE_SCOPES
                )
            except json.JSONDecodeError:
                credentials = service_account.Credentials.from_service_account_file(
                    self.service_account_json, scopes=DRIVE_SCOPES
                )
            self._session = AuthorizedSession(credentials)
        return self._session

    def archive(self, candidate: CandidateIssuance) -> ArchiveResult:
        """Never raises (see module docstring) -- always returns an
        ArchiveResult, succeeded=False with .error set on any failure."""
        if not self.service_account_json or not self.folder_id:
            return ArchiveResult(
                succeeded=False,
                error="GOOGLE_SERVICE_ACCOUNT_JSON/DRIVE_FOLDER_ID not configured.",
            )

        try:
            doc_response = requests.get(
                candidate.source_url,
                timeout=self.FETCH_TIMEOUT_SEC,
                headers={"User-Agent": "Mozilla/5.0 (compatible; RegulatoryScraperArchiver/1.0)"},
            )
            doc_response.raise_for_status()
            content_type = doc_response.headers.get("Content-Type", "application/octet-stream")
            filename = _safe_filename(candidate, content_type)

            session = self._get_session()

            metadata = {"name": filename, "parents": [self.folder_id]}
            files = {
                "metadata": ("metadata", json.dumps(metadata), "application/json; charset=UTF-8"),
                "file": (filename, doc_response.content, content_type.split(";")[0].strip()),
            }
            upload_response = session.post(DRIVE_UPLOAD_URL, files=files, timeout=self.UPLOAD_TIMEOUT_SEC)
            upload_response.raise_for_status()
            uploaded = upload_response.json()
            file_id = uploaded["id"]

            permission_response = session.post(
                DRIVE_PERMISSIONS_URL_TEMPLATE.format(file_id=file_id),
                json={"role": "reader", "type": "anyone"},
                timeout=self.UPLOAD_TIMEOUT_SEC,
            )
            permission_response.raise_for_status()

            link = uploaded.get("webViewLink") or f"https://drive.google.com/file/d/{file_id}/view"
            return ArchiveResult(succeeded=True, archived_document_link=link)
        except Exception as e:
            # Fail-open, same rule Assess follows (§3.8): never let a
            # best-effort failure block or delay the deterministic briefing.
            detail = _describe_exception(e)
            logger.error(
                f"[{candidate.source_regulator}] Archive failed for "
                f"{candidate.issuance_identifier}: {detail}"
            )
            return ArchiveResult(succeeded=False, error=detail)
