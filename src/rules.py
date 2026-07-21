from __future__ import annotations

import logging
from typing import Any


class Rules:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def evaluate(self, data: dict[str, Any]) -> bool:
        # TODO: implement rule evaluation logic
        return True
