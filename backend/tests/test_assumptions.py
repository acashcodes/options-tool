"""Tests for assumptions module (TNX scaling)."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from assumptions import tnx_to_yield_decimal, tnx_to_yield_percent


class TestTNXScaling:
    def test_tnx_to_yield_decimal(self):
        assert tnx_to_yield_decimal(44.5) == pytest.approx(0.0445, abs=1e-6)

    def test_tnx_to_yield_decimal_zero(self):
        assert tnx_to_yield_decimal(0) == 0.0

    def test_tnx_to_yield_decimal_none(self):
        assert tnx_to_yield_decimal(None) is None

    def test_tnx_to_yield_percent(self):
        assert tnx_to_yield_percent(44.5) == pytest.approx(4.45, abs=0.01)

    def test_tnx_to_yield_percent_none(self):
        assert tnx_to_yield_percent(None) is None
