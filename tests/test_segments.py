"""Tests for loats.segments — per-segment sessions, holidays, enablement.

Contract (01Oct2026 wave):
- NSE window 09:15-15:30 IST matches the pre-existing scheduler contract.
- MCX 09:00-23:30 and trades through most NSE holidays (verified live
  calendar: MCX closed only 4 days in 2026; Dussehra 2026-10-20 NSE shut,
  MCX open).
- CDS 09:00-17:00.
- enabled_segments() defaults to NSE-only (behavior-preserving).
"""

from __future__ import annotations

import datetime
from zoneinfo import ZoneInfo

import pytest

from loats import segments as segments_mod
from loats.config.settings import Settings
from loats.segments import (
    MCX_HOLIDAYS_2026,
    NSE_HOLIDAYS_2026,
    enabled_segments,
    is_segment_open,
    segment_for_exchange,
)


class _StubSettings:
    """Settings stub for deterministic clock/segment tests."""

    def __init__(self, enabled: list[str] | None = None) -> None:
        self.timezone = "Asia/Kolkata"
        self.enabled_segments = enabled if enabled is not None else ["NSE"]


def _ist(y: int, m: int, d: int, hh: int, mm: int) -> datetime.datetime:
    return datetime.datetime(y, m, d, hh, mm, tzinfo=ZoneInfo("Asia/Kolkata"))


class TestSessionWindows:
    def test_nse_boundaries_match_scheduler_contract(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings())
        assert _ist(2026, 10, 6, 9, 14).weekday() < 5  # Tuesday sanity
        assert is_segment_open("NSE", _ist(2026, 10, 6, 9, 14)) is False
        assert is_segment_open("NSE", _ist(2026, 10, 6, 9, 15)) is True
        assert is_segment_open("NSE", _ist(2026, 10, 6, 15, 30)) is True
        assert is_segment_open("NSE", _ist(2026, 10, 6, 15, 31)) is False

    def test_mcx_extended_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings())
        assert is_segment_open("MCX", _ist(2026, 10, 6, 8, 59)) is False
        assert is_segment_open("MCX", _ist(2026, 10, 6, 9, 0)) is True
        assert is_segment_open("MCX", _ist(2026, 10, 6, 23, 30)) is True
        assert is_segment_open("MCX", _ist(2026, 10, 6, 23, 31)) is False

    def test_mcx_open_dussehra_when_nse_shut(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """2026-10-20 Dussehra: NSE closed, MCX open evening (live calendar)."""
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings())
        assert is_segment_open("NSE", _ist(2026, 10, 20, 19, 0)) is False
        assert is_segment_open("MCX", _ist(2026, 10, 20, 19, 0)) is True

    def test_cds_session(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings())
        assert is_segment_open("CDS", _ist(2026, 10, 6, 16, 59)) is True
        assert is_segment_open("CDS", _ist(2026, 10, 6, 17, 1)) is False

    def test_weekend_closed_all_segments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings())
        sunday = _ist(2026, 10, 4, 11, 0)
        assert sunday.weekday() == 6
        for seg in ("NSE", "MCX", "CDS"):
            assert is_segment_open(seg, sunday) is False

    def test_gandhi_jayanti_all_closed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """2026-10-02: verified all-segment holiday (live calendar)."""
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings())
        for seg in ("NSE", "MCX", "CDS"):
            assert is_segment_open(seg, _ist(2026, 10, 2, 11, 0)) is False


class TestHolidayCalendars:
    def test_mcx_holiday_calendar_is_minimal_subset(self) -> None:
        """Every MCX closed day is also an NSE closed day (live-verified)."""
        assert MCX_HOLIDAYS_2026 <= NSE_HOLIDAYS_2026
        assert len(MCX_HOLIDAYS_2026) == 4  # Republic Day, Good Friday,
        # Gandhi Jayanti, Christmas — 2026 live calendar.

    def test_exchange_mapping(self) -> None:
        assert segment_for_exchange("NFO") == "NSE"
        assert segment_for_exchange("nse") == "NSE"
        assert segment_for_exchange("MCX") == "MCX"
        assert segment_for_exchange("CDS") == "CDS"
        with pytest.raises(ValueError):
            segment_for_exchange("BOGUS")


class TestSettingsParsing:
    """ENABLED_SEGMENTS env forms (NoDecode contract, 01Oct wave).

    Regression pins: pydantic-settings JSON-decodes complex fields before
    validators, so the operator comma form died with SettingsError until
    the field was annotated NoDecode (185-test error cascade 01Oct).
    Settings(_env_file=None) isolates these probes from the operator .env.
    """

    @staticmethod
    def _settings(monkeypatch: pytest.MonkeyPatch, raw: str | None) -> Settings:
        from loats.config.settings import Settings

        if raw is None:
            monkeypatch.delenv("ENABLED_SEGMENTS", raising=False)
        else:
            monkeypatch.setenv("ENABLED_SEGMENTS", raw)
        # _env_file='' skips the operator .env entirely; the kwarg is
        # pydantic-settings' documented init override, unseen by stubs.
        return Settings(_env_file="")  # type: ignore[call-arg]

    def test_default_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, None)
        assert s.enabled_segments == ["NSE"]

    def test_comma_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, "NSE,MCX")
        assert s.enabled_segments == ["NSE", "MCX"]

    def test_comma_form_lowercased_and_spaced(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        s = self._settings(monkeypatch, "nse, cds")
        assert s.enabled_segments == ["NSE", "CDS"]

    def test_json_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, '["MCX","CDS"]')
        assert s.enabled_segments == ["MCX", "CDS"]

    def test_single_segment(self, monkeypatch: pytest.MonkeyPatch) -> None:
        s = self._settings(monkeypatch, "CDS")
        assert s.enabled_segments == ["CDS"]


class TestEnablement:
    def test_default_is_nse_only(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings())
        assert enabled_segments() == ("NSE",)

    def test_canonical_ordering_regardless_of_config_order(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            segments_mod, "get_settings", lambda: _StubSettings(["CDS", "MCX"])
        )
        assert enabled_segments() == ("MCX", "CDS")

    def test_all_segments(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            segments_mod, "get_settings", lambda: _StubSettings(["nse", "mcx", "cds"])
        )
        assert enabled_segments() == ("NSE", "MCX", "CDS")

    def test_empty_config_falls_back_to_nse(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(segments_mod, "get_settings", lambda: _StubSettings([]))
        assert enabled_segments() == ("NSE",)
