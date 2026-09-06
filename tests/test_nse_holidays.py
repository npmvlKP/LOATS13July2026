"""
Unit tests for NSE holiday calendar (R5-F-08).

Tests verify that known holidays (Republic Day, Diwali, etc.) are correctly
included in the NSE_HOLIDAYS frozenset.
"""

import datetime

import pytest

from loats.scheduler import _NSE_HOLIDAY_TUPLES, NSE_HOLIDAYS


class TestNSEHolidays:
    """Test NSE trading holidays calendar."""

    def test_nse_holidays_is_frozenset(self):
        """Verify NSE_HOLIDAYS is a frozenset for O(1) lookup."""
        assert isinstance(NSE_HOLIDAYS, frozenset), (
            "NSE_HOLIDAYS must be a frozenset for efficient O(1) lookup"
        )

    def test_nse_holidays_are_date_objects(self):
        """Verify all entries are datetime.date objects."""
        for holiday in NSE_HOLIDAYS:
            assert isinstance(holiday, datetime.date), (
                f"Holiday {holiday} must be a datetime.date object"
            )

    def test_holiday_tuples_format(self):
        """Verify _NSE_HOLIDAY_TUPLES format is (year, month, day)."""
        for holiday_tuple in _NSE_HOLIDAY_TUPLES:
            assert isinstance(holiday_tuple, tuple), (
                f"Holiday {holiday_tuple} must be a tuple"
            )
            assert len(holiday_tuple) == 3, (
                f"Holiday tuple {holiday_tuple} must have 3 elements (year, month, day)"
            )
            year, month, day = holiday_tuple
            assert isinstance(year, int) and year >= 2026, (
                f"Year {year} must be an int >= 2026"
            )
            assert isinstance(month, int) and 1 <= month <= 12, (
                f"Month {month} must be an int between 1 and 12"
            )
            assert isinstance(day, int) and 1 <= day <= 31, (
                f"Day {day} must be an int between 1 and 31"
            )

    def test_2026_republic_day(self):
        """Verify Republic Day 2026 (January 26) is a holiday."""
        republic_day_2026 = datetime.date(2026, 1, 26)
        assert republic_day_2026 in NSE_HOLIDAYS, (
            "Republic Day 2026 (January 26) must be a holiday"
        )

    def test_2026_gandhi_jayanti(self):
        """Verify Gandhi Jayanti 2026 (October 2) is a holiday."""
        gandhi_jayanti_2026 = datetime.date(2026, 10, 2)
        assert gandhi_jayanti_2026 in NSE_HOLIDAYS, (
            "Gandhi Jayanti 2026 (October 2) must be a holiday"
        )

    def test_2026_dussehra(self):
        """Verify Dussehra 2026 (October 20) is a holiday."""
        dussehra_2026 = datetime.date(2026, 10, 20)
        assert dussehra_2026 in NSE_HOLIDAYS, (
            "Dussehra 2026 (October 20) must be a holiday"
        )

    def test_2026_diwali(self):
        """Verify Diwali 2026 (November 10) is a holiday."""
        diwali_2026 = datetime.date(2026, 11, 10)
        assert diwali_2026 in NSE_HOLIDAYS, (
            "Diwali 2026 (November 10) must be a holiday"
        )

    def test_2026_christmas(self):
        """Verify Christmas 2026 (December 25) is a holiday."""
        christmas_2026 = datetime.date(2026, 12, 25)
        assert christmas_2026 in NSE_HOLIDAYS, (
            "Christmas 2026 (December 25) must be a holiday"
        )

    def test_2027_republic_day(self):
        """Verify Republic Day 2027 (January 26) is a holiday."""
        republic_day_2027 = datetime.date(2027, 1, 26)
        assert republic_day_2027 in NSE_HOLIDAYS, (
            "Republic Day 2027 (January 26) must be a holiday"
        )

    def test_2027_independence_day(self):
        """Verify Independence Day 2027 (August 15) is a holiday."""
        independence_day_2027 = datetime.date(2027, 8, 15)
        assert independence_day_2027 in NSE_HOLIDAYS, (
            "Independence Day 2027 (August 15) must be a holiday"
        )

    def test_2027_gandhi_jayanti(self):
        """Verify Gandhi Jayanti 2027 (October 2) is a holiday."""
        gandhi_jayanti_2027 = datetime.date(2027, 10, 2)
        assert gandhi_jayanti_2027 in NSE_HOLIDAYS, (
            "Gandhi Jayanti 2027 (October 2) must be a holiday"
        )

    def test_2027_dussehra(self):
        """Verify Dussehra 2027 (October 10) is a holiday."""
        dussehra_2027 = datetime.date(2027, 10, 10)
        assert dussehra_2027 in NSE_HOLIDAYS, (
            "Dussehra 2027 (October 10) must be a holiday"
        )

    def test_2027_diwali(self):
        """Verify Diwali 2027 (October 29) is a holiday."""
        diwali_2027 = datetime.date(2027, 10, 29)
        assert diwali_2027 in NSE_HOLIDAYS, "Diwali 2027 (October 29) must be a holiday"

    def test_2027_christmas(self):
        """Verify Christmas 2027 (December 25) is a holiday."""
        christmas_2027 = datetime.date(2027, 12, 25)
        assert christmas_2027 in NSE_HOLIDAYS, (
            "Christmas 2027 (December 25) must be a holiday"
        )

    def test_2028_republic_day(self):
        """Verify Republic Day 2028 (January 26) is a holiday."""
        republic_day_2028 = datetime.date(2028, 1, 26)
        assert republic_day_2028 in NSE_HOLIDAYS, (
            "Republic Day 2028 (January 26) must be a holiday"
        )

    def test_2028_independence_day(self):
        """Verify Independence Day 2028 (August 15) is a holiday."""
        independence_day_2028 = datetime.date(2028, 8, 15)
        assert independence_day_2028 in NSE_HOLIDAYS, (
            "Independence Day 2028 (August 15) must be a holiday"
        )

    def test_2028_gandhi_jayanti(self):
        """Verify Gandhi Jayanti 2028 (October 2) is a holiday."""
        gandhi_jayanti_2028 = datetime.date(2028, 10, 2)
        assert gandhi_jayanti_2028 in NSE_HOLIDAYS, (
            "Gandhi Jayanti 2028 (October 2) must be a holiday"
        )

    def test_2028_dussehra(self):
        """Verify Dussehra 2028 (October 17) is a holiday."""
        dussehra_2028 = datetime.date(2028, 10, 17)
        assert dussehra_2028 in NSE_HOLIDAYS, (
            "Dussehra 2028 (October 17) must be a holiday"
        )

    def test_2028_diwali(self):
        """Verify Diwali 2028 (November 2) is a holiday."""
        diwali_2028 = datetime.date(2028, 11, 2)
        assert diwali_2028 in NSE_HOLIDAYS, "Diwali 2028 (November 2) must be a holiday"

    def test_2028_christmas(self):
        """Verify Christmas 2028 (December 25) is a holiday."""
        christmas_2028 = datetime.date(2028, 12, 25)
        assert christmas_2028 in NSE_HOLIDAYS, (
            "Christmas 2028 (December 25) must be a holiday"
        )

    def test_2026_holi(self):
        """Verify Holi 2026 (March 3) is a holiday."""
        holi_2026 = datetime.date(2026, 3, 3)
        assert holi_2026 in NSE_HOLIDAYS, "Holi 2026 (March 3) must be a holiday"

    def test_2027_holi(self):
        """Verify Holi 2027 (March 6) is a holiday."""
        holi_2027 = datetime.date(2027, 3, 6)
        assert holi_2027 in NSE_HOLIDAYS, "Holi 2027 (March 6) must be a holiday"

    def test_2028_holi(self):
        """Verify Holi 2028 (February 27) is a holiday."""
        holi_2028 = datetime.date(2028, 2, 27)
        assert holi_2028 in NSE_HOLIDAYS, "Holi 2028 (February 27) must be a holiday"

    def test_2026_ganesh_chaturthi(self):
        """Verify Ganesh Chaturthi 2026 (September 14) is a holiday."""
        ganesh_2026 = datetime.date(2026, 9, 14)
        assert ganesh_2026 in NSE_HOLIDAYS, (
            "Ganesh Chaturthi 2026 (September 14) must be a holiday"
        )

    def test_2027_ganesh_chaturthi(self):
        """Verify Ganesh Chaturthi 2027 (September 4) is a holiday."""
        ganesh_2027 = datetime.date(2027, 9, 4)
        assert ganesh_2027 in NSE_HOLIDAYS, (
            "Ganesh Chaturthi 2027 (September 4) must be a holiday"
        )

    def test_2028_ganesh_chaturthi(self):
        """Verify Ganesh Chaturthi 2028 (September 27) is a holiday."""
        ganesh_2028 = datetime.date(2028, 9, 27)
        assert ganesh_2028 in NSE_HOLIDAYS, (
            "Ganesh Chaturthi 2028 (September 27) must be a holiday"
        )

    def test_weekend_holidays_documented(self):
        """Document any holidays that fall on weekends for awareness."""
        weekend_holidays = [
            holiday for holiday in NSE_HOLIDAYS if holiday.weekday() in [5, 6]
        ]
        # Log for awareness - NSE holidays on weekends are typically
        # trading holidays that fall on weekends
        if weekend_holidays:
            logger = __import__("logging").getLogger(__name__)
            for holiday in weekend_holidays:
                logger.info(
                    "Holiday falls on weekend: %s (%s)", holiday, holiday.strftime("%A")
                )

    def test_frozenset_immutability(self):
        """Verify NSE_HOLIDAYS is a frozenset (immutable)."""
        # Frozensets are unordered by design, so we can't test sorting
        # But we can verify it's a proper frozenset
        assert isinstance(NSE_HOLIDAYS, frozenset), (
            "NSE_HOLIDAYS must be a frozenset for thread safety"
        )
        # Verify we can't modify it
        with pytest.raises(AttributeError):
            NSE_HOLIDAYS.add(datetime.date(2026, 1, 1))  # type: ignore[attr-defined]

    def test_minimum_holiday_count(self):
        """Verify at least 50 holidays are defined across 3 years."""
        # NSE typically has ~15-20 holidays per year
        # With 3 years, we should have at least 45-60 holidays
        assert len(NSE_HOLIDAYS) >= 50, (
            f"Expected at least 50 holidays across 3 years, got {len(NSE_HOLIDAYS)}"
        )

    def test_year_coverage(self):
        """Verify holidays cover at least 2026, 2027, and 2028."""
        years_in_calendar = {holiday.year for holiday in NSE_HOLIDAYS}
        assert 2026 in years_in_calendar, "Calendar must include 2026 holidays"
        assert 2027 in years_in_calendar, "Calendar must include 2027 holidays"
        assert 2028 in years_in_calendar, "Calendar must include 2028 holidays"

    def test_no_duplicate_dates(self):
        """Verify no duplicate holiday dates."""
        holiday_list = list(NSE_HOLIDAYS)
        assert len(holiday_list) == len(set(holiday_list)), (
            "NSE_HOLIDAYS must not contain duplicate dates"
        )

    def test_2026_all_major_festivals_present(self):
        """Verify major Indian festivals are present in 2026."""
        major_festivals_2026 = {
            datetime.date(2026, 1, 15),  # Pongal
            datetime.date(2026, 1, 26),  # Republic Day
            datetime.date(2026, 3, 3),  # Holi
            datetime.date(2026, 3, 26),  # Ram Navami
            datetime.date(2026, 4, 3),  # Mahavir Jayanti
            datetime.date(2026, 4, 14),  # Dr. B.R. Ambedkar Jayanti
            datetime.date(2026, 5, 1),  # Maharashtra Day
            datetime.date(2026, 5, 28),  # Bakri Id
            datetime.date(2026, 6, 26),  # Eid al-Adha
            datetime.date(2026, 9, 14),  # Ganesh Chaturthi
            datetime.date(2026, 10, 2),  # Gandhi Jayanti
            datetime.date(2026, 10, 20),  # Dussehra
            datetime.date(2026, 11, 10),  # Diwali
            datetime.date(2026, 11, 24),  # Guru Nanak Jayanti
            datetime.date(2026, 12, 25),  # Christmas
        }
        for festival in major_festivals_2026:
            assert festival in NSE_HOLIDAYS, (
                f"Major festival {festival} must be in NSE_HOLIDAYS"
            )
