from src.adapters import BaseAdapter, OpenAlgoAdapter


def test_base_adapter():
    adapter = BaseAdapter()
    assert adapter.connect() is True
    assert adapter.disconnect() is None
    assert adapter.send({}) is None
    assert adapter.receive() is None

def test_openalgo_adapter():
    adapter = OpenAlgoAdapter(base_url="http://test.com", api_key="secret")
    assert adapter.send({}) is None
