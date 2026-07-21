import logging
from typing import Any


class BaseAdapter:
    def __init__(self) -> None:
        self.logger = logging.getLogger(__name__)

    def connect(self) -> bool:
        """Establish connection."""
        return True

    def disconnect(self) -> None:
        """Close connection."""
        pass

    def send(self, data: Any) -> Any | None:
        """Send data."""
        return None

    def receive(self) -> Any | None:
        """Receive data."""
        return None


class OpenAlgoAdapter(BaseAdapter):
    def __init__(self, base_url: str, api_key: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.api_key = api_key

    def send(self, data: Any) -> Any | None:
        """Send order OpenAlgo."""
        self.logger.info(f"Sending {self.base_url}")
        return None
