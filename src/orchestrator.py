import logging
import time
from typing import Any


class Orchestrator:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)
        self._components: dict[str, Any] = {}

    def register(self, name: str, component: Any) -> None:
        """Register component."""
        self._components[name] = component

    def cycle(self) -> dict[str, Any]:
        """Execute one orchestration cycle. Target: <100ms."""
        start_time = time.perf_counter()
        results: dict[str, Any] = {}
        for name, component in self._components.items():
            try:
                if hasattr(component, "execute"):
                    results[name] = component.execute()
            except Exception as e:
                self.logger.error(f"Error {name}: {e}")
                results[name] = None
        elapsed = (time.perf_counter() - start_time) * 1000
        if elapsed > 100:
            self.logger.warning(f"Cycle took {elapsed:.2f}ms (target: <100ms)")
        return results
