"""
Archive step (Foundation §3.6/§4.4, Phase 5).

Best-effort document archiving (Foundation §3.9: "Not a full document
management system -- archiving is convenience, not records-management").

How archiving works now (changed 2026-10-06): this step fetches the source
document and hands its bytes back so the email channel can ATTACH it to the
briefing (core/notify_channels.py). It no longer uploads anywhere itself.
The Google Drive upload was dropped because a service account has no storage
quota in a normal "My Drive" folder (confirmed live 2026-09-30), and the only
fix -- a Shared Drive -- needs a Workspace admin, i.e. IT. The email itself is
now the archive: recipients open the file directly, and a copy sits in the
sending mailbox's Sent folder. An optional Google Apps Script in Jas's own
account can copy attachments into her Drive (docs/Drive-Attachment-Copier.gs).

Approved best-effort failure behavior (frozen, §3.8, same rule Phase 4/Assess
follows): if this fails for any reason (network error, proxy error, file too
large), Compose must still produce a Briefing Record from deterministic data
alone, with the missing section explicitly marked -- never silently
incomplete, never withheld. This module enforces that by never raising:
archive() always returns an ArchiveResult, with .succeeded=False and an
.error on any failure.
"""

import logging
import mimetypes
import re
from dataclasses import dataclass, field
from typing import Optional

from core.http_client import ScrapingHttpClient
from models.issuance import CandidateIssuance

logger = logging.getLogger(__name__)

# Same sources that need the ScraperAPI proxy for their listing pages
# (core/adapters/ic_adapter.py, sec_adapter.py) also need it for individual
# document URLs -- insurance.gov.ph and sec.gov.ph block direct requests
# from GitHub Actions' IP ranges regardless of which page on the site is
# being fetched. Confirmed live 2026-09-28: every un-proxied archive attempt
# for IC/SEC got a 403, while BIR (not proxy-gated) had no such failures.
PROXY_REQUIRED_REGULATORS = {"IC", "SEC"}

# Per-document cap. Gmail rejects messages over ~25 MB in total, and one
# digest email can carry several documents, so a single file is capped well
# below that. An over-cap document is treated as an archive failure (field
# marked UNAVAILABLE, briefing still goes out with the official source link).
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024

# Text shown in the briefing's "Archived Copy" column on success.
ATTACHED_LABEL = "Attached to this email"

_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9]+")


def _describe_exception(err: BaseException, max_depth: int = 4) -> str:
    """Renders an exception together with its underlying cause chain, same
    as core/assess.py's helper of the same name -- a bare str(err) can hide
    the actionable detail in __cause__ (see assess.py's 2026-09-04 incident).
    Duplicated rather than imported to keep this module's only real
    dependencies scoped to what Archive itself needs.

    For an HTTPError specifically (e.g. a proxy-relayed 403), requests'
    raise_for_status() only puts the generic "403 Client Error: Forbidden
    for url: ..." into str(err), so this also appends response.text
    (truncated) whenever the exception carries an HTTP response."""
    parts = []
    seen = set()
    current: Optional[BaseException] = err
    depth = 0
    while current is not None and depth < max_depth and id(current) not in seen:
        seen.add(id(current))
        text = str(current).strip() or "(no message)"
        parts.append(f"{type(current).__name__}: {text}")
        response = getattr(current, "response", None)
        if response is not None:
            try:
                body = response.text.strip()
            except Exception:
                body = ""
            if body:
                parts.append(f"response body: {body[:500]}")
        current = current.__cause__ or current.__context__
        depth += 1
    return " <- ".join(parts)


def _safe_filename(candidate: CandidateIssuance, content_type: Optional[str]) -> str:
    """Standard attachment filename: REGULATOR_TYPE_NUMBER.ext, e.g.
    BIR_RMC_RMC-No-61-2026.pdf, IC_CL_<identifier>.pdf, SEC_MC_<identifier>.pdf.

    TYPE is the category without its regulator prefix (IC-CL -> CL). The three
    parts are joined by "_" and nothing inside a part contains "_", so the
    name splits back into regulator/type/number unambiguously -- the optional
    Drive-copy script (docs/Drive-Attachment-Copier.gs) relies on this to file
    each document under REGULATOR/TYPE folders. Extension is guessed from the
    response's Content-Type (none if unrecognized -- mail clients still
    save/open the file fine without one)."""
    regulator = _SAFE_NAME_RE.sub("-", candidate.source_regulator.upper()).strip("-") or "UNKNOWN"
    doc_type = candidate.source_category.upper()
    if doc_type.startswith(f"{candidate.source_regulator.upper()}-"):
        doc_type = doc_type[len(candidate.source_regulator) + 1:]
    doc_type = _SAFE_NAME_RE.sub("-", doc_type).strip("-") or "GENERAL"
    number = _SAFE_NAME_RE.sub("-", candidate.issuance_identifier).strip("-")[:120] or "issuance"
    ext = mimetypes.guess_extension((content_type or "").split(";")[0].strip()) if content_type else None
    return f"{regulator}_{doc_type}_{number}{ext or ''}"


@dataclass
class ArchiveResult:
    succeeded: bool
    archived_document_link: str = "UNAVAILABLE"
    error: Optional[str] = None
    # Populated only on success: the fetched document, to be attached to the
    # briefing email by the notification channel.
    attachment_filename: Optional[str] = None
    attachment_content_type: Optional[str] = None
    attachment_bytes: Optional[bytes] = field(default=None, repr=False)


class Archiver:
    """Best-effort document fetch-for-attachment (Phase 5).

    Needs no credentials of its own. IC/SEC documents are fetched through the
    same SCRAPER_PROXY_API_KEY proxy their listing pages use; BIR is fetched
    directly.
    """

    def __init__(self):
        self.http_client = ScrapingHttpClient()

    def archive(self, candidate: CandidateIssuance) -> ArchiveResult:
        """Never raises (see module docstring) -- always returns an
        ArchiveResult, succeeded=False with .error set on any failure."""
        try:
            use_proxy = candidate.source_regulator.upper() in PROXY_REQUIRED_REGULATORS
            doc_content, content_type = self.http_client.fetch_bytes(
                candidate.source_regulator, candidate.source_url, use_proxy=use_proxy
            )

            if not doc_content:
                raise ValueError("Fetched document was empty.")
            if len(doc_content) > MAX_ATTACHMENT_BYTES:
                raise ValueError(
                    f"Document is {len(doc_content) / (1024 * 1024):.1f} MB, over the "
                    f"{MAX_ATTACHMENT_BYTES // (1024 * 1024)} MB per-document attachment limit."
                )

            clean_type = (content_type or "application/octet-stream").split(";")[0].strip()
            return ArchiveResult(
                succeeded=True,
                archived_document_link=ATTACHED_LABEL,
                attachment_filename=_safe_filename(candidate, clean_type),
                attachment_content_type=clean_type,
                attachment_bytes=doc_content,
            )
        except Exception as e:
            # Fail-open, same rule Assess follows (§3.8): never let a
            # best-effort failure block or delay the deterministic briefing.
            detail = _describe_exception(e)
            logger.error(
                f"[{candidate.source_regulator}] Archive failed for "
                f"{candidate.issuance_identifier}: {detail}"
            )
            return ArchiveResult(succeeded=False, error=detail)
