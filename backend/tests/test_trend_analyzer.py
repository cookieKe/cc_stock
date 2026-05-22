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
        assert len(tps) == 0  # 103 peak never confirmed (no 5% drop after it before data ends)

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
        # Recent data with clear pattern (at least 5 points to avoid early return)
        recent = [100, 108, 92, 105, 103, 110]  # up 8%, down 15%, up 14%, down 2%, up 7%
        older = [95, 102, 98, 103, 97]  # older noisy data
        df_recent = make_df(recent, start_date=datetime(2026, 1, 20))
        df_full = make_df(older + recent)

        ta = TrendAnalyzer(threshold=0.05)
        result_full = ta.analyze(df_full)
        result_recent = ta.analyze(df_recent)

        # The last turning point type should match
        assert result_full['turning_points'], "Full data should produce turning points"
        assert result_recent['turning_points'], "Recent data should produce turning points"
        assert result_full['turning_points'][-1]['type'] == result_recent['turning_points'][-1]['type']


class TestTrendClassification:
    def test_strong_up(self):
        """Higher highs and higher lows = strong_up."""
        # zigzag with rising peaks (110→120) and rising troughs (80→90)
        prices = [100, 90, 110, 80, 120, 90, 130]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'strong_up'

    def test_strong_down(self):
        """Lower highs and lower lows = strong_down."""
        # zigzag with falling peaks (100→95) and falling troughs (90→80)
        prices = [130, 110, 90, 100, 80, 95, 70]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'strong_down'

    def test_slow_up_higher_high_flat_low(self):
        """Higher high but trough not significantly higher = slow_up."""
        # 1 peak + 1 trough, last tp is trough → slow_up
        prices = [100, 110, 95, 105, 115]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'slow_up'

    def test_slow_down(self):
        """Lower low but peak not significantly lower = slow_down."""
        # 1 trough + 1 peak, last tp is peak → slow_down
        prices = [110, 100, 95, 105, 90]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'slow_down'

    def test_sideways(self):
        """No clear pattern = sideways."""
        prices = [100, 103, 99, 102, 98, 101]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        # Within 3% range — no turning points → sideways
        assert result['trend'] == 'sideways'

    def test_few_points(self):
        """Less than 5 data points = sideways."""
        prices = [100, 105, 110, 115]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'sideways'
        assert result['turning_points'] == []


class TestStrength:
    def test_strong_trend_high_score(self):
        """A strong persistent trend should have a high strength score."""
        # 4 zigzags ending with peak → slope + persistence give score > 50
        prices = [100, 80, 115, 85, 130, 95, 145, 100]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['strength']['score'] > 50
        assert result['strength']['persistence'] >= 2

    def test_sideways_zero_persistence(self):
        """Sideways trend = persistence 0."""
        prices = [100, 102, 99, 101, 98]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'sideways'
        assert result['strength']['persistence'] == 0

    def test_last_high_low(self):
        """Should return the most recent peak and trough prices."""
        prices = [100, 110, 95, 108, 103]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['last_high'] is not None
        assert result['last_low'] is not None
        # last_low should be around 95
        assert 93 <= result['last_low'] <= 97


class TestEdgeCases:
    def test_nan_in_data(self):
        """NaN values should be forward-filled."""
        prices = [100, np.nan, 105, 110, np.nan, 105, 100, 95]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['turning_points']  # should not crash

    def test_lookback(self):
        """lookback should limit the analysis window."""
        # Older data has strong pattern, newer data flat
        prices = (
            [100, 110, 100, 110, 100] +   # old: clear zigzag
            [100, 101, 100, 101, 100]      # new: flat
        )
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)

        # Full data: should find turning points from old section
        full = ta.analyze(df)
        assert len(full['turning_points']) >= 2

        # Only last 5: flat data, no turning points
        recent = ta.analyze(df, lookback=5)
        assert recent['turning_points'] == []

    def test_lookback_larger_than_data(self):
        """lookback > data length should use all data."""
        prices = [100, 110, 95, 108, 103]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df, lookback=100)
        assert len(result['turning_points']) >= 1

    def test_threshold_validation(self):
        """Invalid threshold should raise ValueError."""
        with pytest.raises(ValueError):
            TrendAnalyzer(threshold=0)
        with pytest.raises(ValueError):
            TrendAnalyzer(threshold=1.5)
        with pytest.raises(ValueError):
            TrendAnalyzer(threshold=-0.1)
