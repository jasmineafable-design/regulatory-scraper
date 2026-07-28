import pytest
from unittest.mock import patch, MagicMock
from src.adapters.ic import ICAdapter
from src.adapters.sec import SECAdapter

def test_ic_adapter_instantiation():
    adapter = ICAdapter()
    assert adapter.BASE_URL == "https://www.insurance.gov.ph"

def test_sec_adapter_instantiation():
    adapter = SECAdapter()
    assert adapter.BASE_URL == "https://www.sec.gov.ph"

@patch("requests.get")
def test_ic_adapter_fetch_mock(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<article><a href='https://ic.gov.ph/cl1'>IC Circular 2026-01</a></article>"
    mock_get.return_value = mock_response

    adapter = ICAdapter()
    results = adapter.fetch()

    assert len(results) == 1
    assert results[0]["regulator"] == "IC"
    assert results[0]["title"] == "IC Circular 2026-01"

@patch("requests.get")
def test_sec_adapter_fetch_mock(mock_get):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = "<table><tr><td>SEC MC No. 1</td><td><a href='https://sec.gov.ph/mc1'>Download</a></td></tr></table>"
    mock_get.return_value = mock_response

    adapter = SECAdapter()
    results = adapter.fetch()

    assert len(results) == 1
    assert results[0]["regulator"] == "SEC"
    assert results[0]["title"] == "SEC MC No. 1"
