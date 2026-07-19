from unittest.mock import MagicMock

import pytest

from src.orchestrator import Orchestrator


@pytest.fixture
def orchestrator():
    return Orchestrator()

def test_orchestrator_registration(orchestrator):
    mock_component = MagicMock()
    orchestrator.register("test", mock_component)
    assert orchestrator._components["test"] == mock_component

def test_orchestrator_cycle(orchestrator):
    mock_component = MagicMock()
    mock_component.execute.return_value = "result"
    orchestrator.register("test", mock_component)
    results = orchestrator.cycle()
    assert results["test"] == "result"
    mock_component.execute.assert_called_once()

def test_orchestrator_cycle_error(orchestrator):
    mock_component = MagicMock()
    mock_component.execute.side_effect = Exception("fail")
    orchestrator.register("test", mock_component)
    results = orchestrator.cycle()
    assert results["test"] is None
