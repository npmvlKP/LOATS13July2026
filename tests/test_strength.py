import pytest

from src.strength import Strength


@pytest.fixture
def strength():
    return Strength()


def test_strength(strength):
    assert strength.calculate({}) == 0.5
