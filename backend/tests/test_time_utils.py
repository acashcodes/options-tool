"""Tests for time_utils: timezone-aware expiry math."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from datetime import datetime
from zoneinfo import ZoneInfo

from time_utils import year_frac_to, days_to, expiry_dt_et, now_et, NY_TZ


class TestYearFracTo:
    def test_expiry_day_morning_has_time_left(self):
        """On expiration day at 10 AM ET, there should be time remaining."""
        exp = "2026-03-20"
        as_of = datetime(2026, 3, 20, 10, 0, 0, tzinfo=NY_TZ)
        t = year_frac_to(exp, as_of=as_of)
        assert t > 0, "Morning of expiry should have time remaining"

    def test_expiry_day_after_close_is_zero(self):
        """On expiration day at 5 PM ET, time should be 0."""
        exp = "2026-03-20"
        as_of = datetime(2026, 3, 20, 17, 0, 0, tzinfo=NY_TZ)
        t = year_frac_to(exp, as_of=as_of)
        assert t == 0.0

    def test_past_expiry_is_zero(self):
        exp = "2020-01-01"
        as_of = datetime(2026, 1, 1, 12, 0, 0, tzinfo=NY_TZ)
        assert year_frac_to(exp, as_of=as_of) == 0.0

    def test_one_year_out(self):
        as_of = datetime(2026, 3, 20, 16, 0, 0, tzinfo=NY_TZ)
        exp = "2027-03-20"
        t = year_frac_to(exp, as_of=as_of)
        assert t == pytest.approx(1.0, abs=0.01)


class TestDaysTo:
    def test_next_day_expiry(self):
        as_of = datetime(2026, 3, 19, 10, 0, 0, tzinfo=NY_TZ)
        exp = "2026-03-20"
        d = days_to(exp, as_of=as_of)
        assert 1.0 < d < 2.0

    def test_same_day_morning(self):
        as_of = datetime(2026, 3, 20, 10, 0, 0, tzinfo=NY_TZ)
        exp = "2026-03-20"
        d = days_to(exp, as_of=as_of)
        assert 0 < d < 1


class TestExpiryDtEt:
    def test_returns_4pm_et(self):
        dt = expiry_dt_et("2026-03-20")
        assert dt.hour == 16
        assert dt.minute == 0
        assert dt.tzinfo == NY_TZ


class TestNowEt:
    def test_has_timezone(self):
        n = now_et()
        assert n.tzinfo is not None
