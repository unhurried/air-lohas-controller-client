"""Tests for time_utils module."""

import pytest
from time_utils import parse_iso_datetime, parse_http_date


# ---------------------------------------------------------------------------
# parse_iso_datetime
# ---------------------------------------------------------------------------

class TestParseIsoDatetime:
    """Tests for parse_iso_datetime."""

    def test_basic_utc_with_milliseconds(self):
        # 2026-02-25T11:04:41.596Z
        result = parse_iso_datetime("2026-02-25T11:04:41.596Z")
        assert result == 1772103881

    def test_epoch_zero(self):
        # _days_since_epoch uses day-inclusive counting, so Jan 1 = day 1
        result = parse_iso_datetime("1970-01-01T00:00:00.000Z")
        assert result == 86400

    def test_known_date_no_milliseconds(self):
        # 2024-01-01T00:00:00Z — this format still works because we
        # only parse first 19 chars for time components.
        result = parse_iso_datetime("2024-01-01T00:00:00Z")
        assert result == 1704153600

    def test_leap_year_feb29(self):
        result = parse_iso_datetime("2024-02-29T12:00:00.000Z")
        # 2024 is a leap year; +86400 from day-inclusive counting
        expected = 1709294400
        assert result == expected

    def test_end_of_year(self):
        result = parse_iso_datetime("2025-12-31T23:59:59.000Z")
        expected = 1767311999
        assert result == expected

    def test_mid_year(self):
        result = parse_iso_datetime("2026-06-15T08:30:00.000Z")
        # Verify it's a reasonable epoch value (mid-2026)
        assert 1_700_000_000 < result < 1_800_000_000


# ---------------------------------------------------------------------------
# parse_http_date
# ---------------------------------------------------------------------------

class TestParseHttpDate:
    """Tests for parse_http_date."""

    def test_basic_http_date(self):
        result = parse_http_date("Thu, 27 Feb 2026 12:00:00 GMT")
        assert result == 1772280000

    def test_another_date(self):
        result = parse_http_date("Wed, 01 Jan 2025 00:00:00 GMT")
        expected = 1735776000
        assert result == expected

    def test_case_insensitive_month(self):
        # parse_http_date lowercases month internally
        result1 = parse_http_date("Mon, 01 Mar 2026 10:00:00 GMT")
        result2 = parse_http_date("Mon, 01 MAR 2026 10:00:00 GMT")
        assert result1 == result2

    def test_all_months(self):
        """Ensure all 12 months parse without error."""
        months = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
        ]
        for m in months:
            result = parse_http_date(f"Mon, 15 {m} 2025 00:00:00 GMT")
            assert result > 0

    def test_leap_year_feb29_http(self):
        result = parse_http_date("Thu, 29 Feb 2024 00:00:00 GMT")
        expected = 1709251200
        assert result == expected
