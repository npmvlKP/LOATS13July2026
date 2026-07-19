from decimal import Decimal

import pytest

from src.risk import Risk


@pytest.fixture
def risk():
    return Risk()

def test_risk_evaluate(risk):
    assert risk.evaluate({"test": 1}) is True

def test_calculate_position_size(risk):
    price = Decimal("100")
    # Case 1: volatility < 0.3 -> returns max_position_size * 0.5 = 50000
    volatility = Decimal("0.2")
    size = risk.calculate_position_size(price, volatility)
    assert size == Decimal("50000")

    # Case 2: volatility >= 0.3 -> returns max_position_size = 100000
    volatility = Decimal("0.3")
    size = risk.calculate_position_size(price, volatility)
    assert size == Decimal("100000")
