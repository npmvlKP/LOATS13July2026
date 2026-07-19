import logging


class Rules:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def evaluate(self, data: dict) -> bool:
        # TODO: implement rule evaluation logic
        return True
