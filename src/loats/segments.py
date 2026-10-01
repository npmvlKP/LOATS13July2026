"""Trading-segment registry: per-segment sessions, holidays, and helpers.

Evidence base (verified 01Oct2026):
- All holiday dates generated from OpenAlgo's live
  ``POST /api/v1/market/holidays`` (Zerodha-sourced 2026 calendar), NOT
  hand-curated lists. NSE closed 16 days, MCX closed only 4 days (MCX
  trades through most NSE holidays), CDS closed 16 days.
- Session windows (IST): NSE 09:15-15:30 (pre-existing contract),
  MCX 09:00-23:30, CDS 09:00-17:00.
- ``enabled_segments`` defaults to ``["NSE"]``: current behavior is
  preserved exactly until an operator enables more segments in .env.
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

from .config.settings import get_settings

__all__ = [
    "SEGMENT_SESSIONS",
    "NSE_HOLIDAYS_2026",
    "MCX_HOLIDAYS_2026",
    "CDS_HOLIDAYS_2026",
    "SEGMENT_HOLIDAYS",
    "SEGMENT_EXCHANGE",
    "is_segment_open",
    "segment_for_exchange",
    "enabled_segments",
]

# Session windows in IST, (open, close), 24h "HH:MM".
SEGMENT_SESSIONS: dict[str, tuple[str, str]] = {
    "NSE": ("09:15", "15:30"),
    "MCX": ("09:00", "23:30"),
    "CDS": ("09:00", "17:00"),
}

# 2026 trading holidays, from OpenAlgo /api/v1/market/holidays (01Oct2026).
NSE_HOLIDAYS_2026: frozenset[datetime.date] = frozenset(
    datetime.date(y, m, d)
    for y, m, d in (
        (2026, 1, 15),
        (2026, 1, 26),
        (2026, 3, 3),
        (2026, 3, 26),
        (2026, 3, 31),
        (2026, 4, 3),
        (2026, 4, 14),
        (2026, 5, 1),
        (2026, 5, 28),
        (2026, 6, 26),
        (2026, 9, 14),
        (2026, 10, 2),
        (2026, 10, 20),
        (2026, 11, 10),
        (2026, 11, 24),
        (2026, 12, 25),
    )
)

MCX_HOLIDAYS_2026: frozenset[datetime.date] = frozenset(
    datetime.date(y, m, d)
    for y, m, d in (
        (2026, 1, 26),
        (2026, 4, 3),
        (2026, 10, 2),
        (2026, 12, 25),
    )
)

CDS_HOLIDAYS_2026: frozenset[datetime.date] = frozenset(
    datetime.date(y, m, d)
    for y, m, d in (
        (2026, 1, 15),
        (2026, 1, 26),
        (2026, 3, 3),
        (2026, 3, 26),
        (2026, 3, 31),
        (2026, 4, 3),
        (2026, 4, 14),
        (2026, 5, 1),
        (2026, 5, 28),
        (2026, 6, 26),
        (2026, 9, 14),
        (2026, 10, 2),
        (2026, 10, 20),
        (2026, 11, 10),
        (2026, 11, 24),
        (2026, 12, 25),
    )
)

SEGMENT_HOLIDAYS: dict[str, frozenset[datetime.date]] = {
    "NSE": NSE_HOLIDAYS_2026,
    "MCX": MCX_HOLIDAYS_2026,
    "CDS": CDS_HOLIDAYS_2026,
}

# OpenAlgo/UiT exchange names that belong to each segment (NFO/BFO roll up
# into the NSE equity-session segment; MCX_INDEX/MCX into MCX).
SEGMENT_EXCHANGE: dict[str, str] = {
    "NSE": "NSE",
    "NFO": "NSE",
    "BSE": "NSE",
    "BFO": "NSE",
    "MCX": "MCX",
    "CDS": "CDS",
}


def segment_for_exchange(exchange: str) -> str:
    """Map an exchange code to its session segment. Raises on unknown."""
    seg = SEGMENT_EXCHANGE.get(exchange.strip().upper())
    if seg is None:
        raise ValueError(f"Unknown exchange for segment mapping: {exchange!r}")
    return seg


def _parse_hhmm(value: str) -> tuple[int, int]:
    hour_s, minute_s = value.split(":", 1)
    return int(hour_s), int(minute_s)


def is_segment_open(segment: str, now: datetime.datetime | None = None) -> bool:
    """Whether ``segment`` is inside its trading window at ``now`` (IST).

    Weekday + segment-specific holiday calendar + segment session window.
    Mirrors :func:`loats.scheduler.is_market_open` semantics per segment.
    """
    seg = segment.strip().upper()
    if seg not in SEGMENT_SESSIONS:
        raise ValueError(f"Unknown segment: {segment!r}")

    settings = get_settings()
    tz = ZoneInfo(settings.timezone)
    if now is None:
        now = datetime.datetime.now(tz)
    elif now.tzinfo is None:
        now = now.replace(tzinfo=tz)

    if now.weekday() >= 5:
        return False
    if now.date() in SEGMENT_HOLIDAYS[seg]:
        return False

    open_h, open_m = _parse_hhmm(SEGMENT_SESSIONS[seg][0])
    close_h, close_m = _parse_hhmm(SEGMENT_SESSIONS[seg][1])
    open_dt = now.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    close_dt = now.replace(hour=close_h, minute=close_m, second=0, microsecond=0)
    return open_dt <= now <= close_dt


def enabled_segments() -> tuple[str, ...]:
    """Segments the operator has enabled, in canonical order.

    Default is ``("NSE",)`` -- behavior-preserving until configured.
    """
    settings = get_settings()
    order = ("NSE", "MCX", "CDS")
    configured = tuple(
        s for s in order if s in {x.strip().upper() for x in settings.enabled_segments}
    )
    return configured or ("NSE",)


def any_enabled_segment_open(now: datetime.datetime | None = None) -> bool:
    """True while ANY operator-enabled segment is inside its session.

    Consumed by per-segment strategy producers (MCX/CDS engines land in
    the follow-up wave) so each consults only its own segment gate.
    """
    return any(is_segment_open(seg, now) for seg in enabled_segments())
