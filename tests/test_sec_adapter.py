import pytest
from core.adapters.sec_adapter import SECAdapter
from core.models import CandidateIssuance


def test_sec_adapter_initialization():
    adapter = SECAdapter()
    assert adapter.regulator_id == "SEC"


def test_sec_adapter_fetch_mocked(mocker):
    adapter = SECAdapter()
    
    mock_html = """
    <html>
        <body>
            <a href="https://www.sec.gov.ph/mc-1-2026.pdf">SEC MC No. 1 S. 2026: Rules on Corporate Governance</a>
        </body>
    </html>
    """
    
    mocker.patch("requests.get", return_value=mocker.Mock(status_code=200, text=mock_html))
    
    results = adapter.fetch_latest_issuances()
    assert len(results) == 1
    assert isinstance(results[0], CandidateIssuance)
    assert results[0].regulator_id == "SEC"
    assert "SEC" in results[0].issuance_identifier
