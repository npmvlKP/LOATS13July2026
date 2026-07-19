from src.rules import Rules


def test_rules():
    rules = Rules()
    assert rules.evaluate({}) is True
