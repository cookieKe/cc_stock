"""Tests for TrendAnalyzer."""
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.strategy_engine.trend_analyzer import TrendAnalyzer


def make_df(prices, start_date=None):
    """Helper: create a price DataFrame from a list of close prices."""
    if start_date is None:
        start_date = datetime(2026, 1, 5)
    dates = [start_date + timedelta(days=i) for i in range(len(prices))]
    return pd.DataFrame({'date': dates, 'close': prices})


class TestTurningPoints:
    def test_simple_peak_trough(self):
        """Clear peak-trough-peak pattern should be detected."""
        # Prices: rise 10% -> drop 10% -> rise 10%
        prices = [100, 105, 110, 105, 100, 95, 100, 105, 110]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)

        tps = result['turning_points']
        types = [p['type'] for p in tps]
        # Should find at least: peak near 110, trough near 95
        assert 'peak' in types
        assert 'trough' in types
        # Peak should be around 110
        peaks = [p for p in tps if p['type'] == 'peak']
        assert any(108 <= p['price'] <= 112 for p in peaks)
        # Trough should be around 95
        troughs = [p for p in tps if p['type'] == 'trough']
        assert any(93 <= p['price'] <= 97 for p in troughs)

    def test_small_fluctuations_ignored(self):
        """Sub-threshold fluctuations should not create turning points."""
        # Small 2% wiggles, then a real 10% drop
        prices = [100, 102, 101, 103, 102, 101, 103, 90]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)

        tps = result['turning_points']
        # The 2% wiggles should NOT create turning points
        # Only the 10%+ drop should register (as trough at 90, preceded by a peak)
        assert len(tps) <= 3  # at most peak->trough or just a couple

    def test_threshold_sensitivity(self):
        """Higher threshold = fewer turning points."""
        # Prices with 6% swings
        prices = [100, 106, 100, 106, 100]
        df = make_df(prices)

        ta5 = TrendAnalyzer(threshold=0.05)  # 5% -- should catch 6% swings
        result5 = ta5.analyze(df)
        assert len(result5['turning_points']) >= 2

        ta10 = TrendAnalyzer(threshold=0.10)  # 10% -- should miss 6% swings
        result10 = ta10.analyze(df)
        assert len(result10['turning_points']) == 0

    def test_monotonic_up_no_turning(self):
        """Steady rise without reversals = no turning points."""
        prices = [100, 102, 104, 106, 108, 110]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['turning_points'] == []

    def test_monotonic_down_no_turning(self):
        """Steady decline without reversals = no turning points."""
        prices = [110, 108, 106, 104, 102, 100]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['turning_points'] == []

    def test_scan_from_newest_consistent(self):
        """Adding older data should not change the most recent turning points."""
        # Recent data with clear pattern
        recent = [100, 108, 92, 105]  # up 8%, down 15%, up 14% -- 2 turning points in recent
        older = [95, 102, 98, 103, 97]  # older noisy data
        df_recent = make_df(recent, start_date=datetime(2026, 1, 20))
        df_full = make_df(older + recent)

        ta = TrendAnalyzer(threshold=0.05)
        result_full = ta.analyze(df_full)
        result_recent = ta.analyze(df_recent)

        # The last turning point type should match
        if result_full['turning_points'] and result_recent['turning_points']:
            assert result_full['turning_points'][-1]['type'] == result_recent['turning_points'][-1]['type']
