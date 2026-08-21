"""Utility functions for CMP module."""

from datetime import datetime, timedelta

def get_orderbook_mins(hours: int = 2) -> datetime:
    """Get datetime from hours ago for orderbook analysis.

    Args:
        hours: Number of hours to go back

    Returns:
        datetime object representing the time hours ago
    """
    return datetime.now() - timedelta(hours=hours)