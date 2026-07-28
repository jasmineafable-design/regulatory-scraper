import pytest
from src.adapters.ic import ICAdapter
from src.adapters.sec import SECAdapter

def test_ic_adapter_fetch_interface():
    adapter = ICAdapter()
    result = adapter.fetch()
    assert isinstance(result, list)

def test_sec_adapter_fetch_interface():
    adapter = SECAdapter()
    result = adapter.fetch()
    assert isinstance(result, list)
