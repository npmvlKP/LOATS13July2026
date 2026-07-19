import pytest

from src.strike import Strike


@pytest.fixture
def strike():
    return Strike()

def test_strike(strike):
    result = strike.calculate({})
    assert isinstance(result, dict)
