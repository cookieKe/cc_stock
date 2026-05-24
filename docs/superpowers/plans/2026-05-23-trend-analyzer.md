# TrendAnalyzer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a shared TrendAnalyzer utility that detects significant price turning points via ZigZag algorithm and classifies trends into 5 states.

**Architecture:** Single `TrendAnalyzer` class in `backend/strategy_engine/trend_analyzer.py`. Scans closing prices from newest to oldest using a percentage-threshold ZigZag, then classifies trend direction by comparing consecutive peaks and troughs (Dow Theory). Strength combines slope and persistence into a 0-100 score. No external dependencies beyond numpy/pandas.

**Tech Stack:** Python 3, numpy, pandas (already in project)

---

## File Structure

| File | Role |
|------|------|
| `backend/strategy_engine/trend_analyzer.py` | TrendAnalyzer class — ZigZag detection, trend classification, strength scoring |
| `backend/tests/test_trend_analyzer.py` | Unit tests — turning points, trend states, edge cases |

---

### Task 1: TrendAnalyzer skeleton — turning point detection

**Files:**
- Create: `backend/strategy_engine/trend_analyzer.py`
- Create: `backend/tests/test_trend_analyzer.py`

- [ ] **Step 1: Write the test file with turning-point detection tests**

```python
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
        # Prices: rise 10% → drop 10% → rise 10%
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
        assert len(tps) <= 3  # at most peak→trough or just a couple

    def test_threshold_sensitivity(self):
        """Higher threshold = fewer turning points."""
        # Prices with 6% swings
        prices = [100, 106, 100, 106, 100]
        df = make_df(prices)

        ta5 = TrendAnalyzer(threshold=0.05)  # 5% — should catch 6% swings
        result5 = ta5.analyze(df)
        assert len(result5['turning_points']) >= 2

        ta10 = TrendAnalyzer(threshold=0.10)  # 10% — should miss 6% swings
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
        recent = [100, 108, 92, 105]  # up 8%, down 15%, up 14% — 2 turning points in recent
        older = [95, 102, 98, 103, 97]  # older noisy data
        df_recent = make_df(recent, start_date=datetime(2026, 1, 20))
        df_full = make_df(older + recent)

        ta = TrendAnalyzer(threshold=0.05)
        result_full = ta.analyze(df_full)
        result_recent = ta.analyze(df_recent)

        # The last turning point type should match
        if result_full['turning_points'] and result_recent['turning_points']:
            assert result_full['turning_points'][-1]['type'] == result_recent['turning_points'][-1]['type']
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd C:/Users/cyneuzk/develop/cc_stock && python -m pytest backend/tests/test_trend_analyzer.py -v
```

Expected: ImportError (module not found)

- [ ] **Step 3: Create TrendAnalyzer with `_find_turning_points`**

```python
"""统一趋势分析器 — 基于之字转向算法识别显著高低点并判断趋势."""
import numpy as np
import pandas as pd
from typing import Optional, List, Dict, Any


class TrendAnalyzer:
    """统一趋势分析器.

    从最新数据向最早数据扫描, 基于百分比阈值识别显著转折点,
    再通过道氏理论(高点-高点, 低点-低点比较)判断五态趋势.
    """

    def __init__(self, threshold: float = 0.05):
        if threshold <= 0 or threshold > 1:
            raise ValueError("threshold must be in (0, 1]")
        self.threshold = threshold

    def analyze(self, df: pd.DataFrame, lookback: Optional[int] = None) -> Dict[str, Any]:
        """分析价格趋势.

        Args:
            df: 含 'date', 'close' 列的DataFrame, 按日期升序排列.
            lookback: 仅分析最近N个交易日, None=全部.

        Returns:
            dict with keys: turning_points, trend, strength, last_high, last_low.
        """
        if lookback is not None and len(df) > lookback:
            df = df.iloc[-lookback:]

        closes = df['close'].values.astype(np.float64)
        dates = df['date'].values

        # 前向填充NaN
        closes = pd.Series(closes).ffill().bfill().values

        if len(closes) < 5:
            return self._empty_result()

        turning_points = self._find_turning_points(closes, dates)

        if not turning_points:
            return self._no_turning_result(closes, dates)

        trend = self._classify_trend(turning_points)
        strength = self._calc_strength(turning_points, closes, trend)
        last_high = self._last_of_type(turning_points, 'peak')
        last_low = self._last_of_type(turning_points, 'trough')

        return {
            'turning_points': turning_points,
            'trend': trend,
            'strength': strength,
            'last_high': last_high,
            'last_low': last_low,
        }

    # ── turning point detection ──────────────────────────────────────

    def _find_turning_points(self, closes: np.ndarray, dates: np.ndarray) -> List[Dict]:
        """从最新向最早扫描, 用百分比阈值找之字转折点."""
        n = len(closes)
        # 反转: 最新→最早
        prices = closes[::-1]

        turning_rev = []       # newest first
        direction = None       # 'up' or 'down' in scan direction
        extreme_price = float(prices[0])
        extreme_idx = 0        # index in reversed array

        for i in range(1, len(prices)):
            price = float(prices[i])

            if direction is None:
                direction, extreme_price, extreme_idx = self._init_direction(
                    price, i, extreme_price, extreme_idx
                )
                continue

            if direction == 'up':
                # 向后看价格上升 → 跟踪最高点
                if price > extreme_price:
                    extreme_price = price
                    extreme_idx = i
                # 从最高点回落超过阈值 → 峰值
                if (extreme_price - price) / extreme_price >= self.threshold:
                    turning_rev.append(self._make_tp('peak', extreme_price, extreme_idx, dates, n))
                    direction = 'down'
                    extreme_price = price
                    extreme_idx = i
            else:
                # 向后看价格下降 → 跟踪最低点
                if price < extreme_price:
                    extreme_price = price
                    extreme_idx = i
                # 从最低点反弹超过阈值 → 谷底
                if (price - extreme_price) / extreme_price >= self.threshold:
                    turning_rev.append(self._make_tp('trough', extreme_price, extreme_idx, dates, n))
                    direction = 'up'
                    extreme_price = price
                    extreme_idx = i

        # 翻转为时间升序
        turning_rev.reverse()
        return turning_rev

    def _init_direction(self, price, idx, extreme_price, extreme_idx):
        """确定初始扫描方向."""
        change_up = (price - extreme_price) / extreme_price
        change_down = (extreme_price - price) / extreme_price

        if change_up >= self.threshold:
            return 'up', max(price, extreme_price), idx if price > extreme_price else extreme_idx
        elif change_down >= self.threshold:
            return 'down', min(price, extreme_price), idx if price < extreme_price else extreme_idx
        else:
            # 方向仍不明确, 更新极值
            if price > extreme_price:
                return None, price, idx
            elif price < extreme_price:
                return None, price, idx
            return None, extreme_price, extreme_idx

    def _make_tp(self, tp_type, price, rev_idx, dates, n):
        """构造转折点字典, 将反转索引映射回原始索引."""
        orig_idx = n - 1 - rev_idx
        return {
            'type': tp_type,
            'date': str(dates[orig_idx])[:10],
            'price': round(float(price), 2),
            'index': orig_idx,
        }

    # ── trend classification ─────────────────────────────────────────

    def _classify_trend(self, turning_points: List[Dict]) -> str:
        """基于最后2组同类型转折点比较, 判断五态趋势."""
        peaks = [p for p in turning_points if p['type'] == 'peak']
        troughs = [p for p in turning_points if p['type'] == 'trough']

        if len(turning_points) < 2:
            return 'sideways'

        if len(peaks) < 2 and len(troughs) < 2:
            last_tp = turning_points[-1]
            return 'slow_down' if last_tp['type'] == 'peak' else 'slow_up'

        if len(peaks) < 2 or len(troughs) < 2:
            return 'sideways'

        prev_peak, last_peak = peaks[-2]['price'], peaks[-1]['price']
        prev_trough, last_trough = troughs[-2]['price'], troughs[-1]['price']

        half = self.threshold * 0.5

        peak_up = (last_peak - prev_peak) / prev_peak > half
        peak_down = (last_peak - prev_peak) / prev_peak < -half
        trough_up = (last_trough - prev_trough) / prev_trough > half
        trough_down = (last_trough - prev_trough) / prev_trough < -half

        if peak_up and trough_up:
            return 'strong_up'
        if peak_up:
            return 'slow_up'
        if peak_down and trough_down:
            return 'strong_down'
        if trough_down:
            return 'slow_down'
        return 'sideways'

    # ── strength calculation ─────────────────────────────────────────

    def _calc_strength(self, turning_points, closes, trend):
        """综合斜率与持续性计算趋势强度."""
        slope = self._calc_slope(turning_points, trend)
        persistence = self._count_persistence(turning_points, trend)
        persistence_norm = min(persistence / 4.0, 1.0)
        score = min(slope * 0.6 + persistence_norm * 0.4 * 100, 100)
        return {
            'slope': round(slope, 2),
            'persistence': persistence,
            'score': round(score, 2),
        }

    def _calc_slope(self, turning_points, trend):
        """计算最后一段趋势线的年化归一化斜率."""
        peaks = [p for p in turning_points if p['type'] == 'peak']
        troughs = [p for p in turning_points if p['type'] == 'trough']

        if trend in ('strong_up', 'slow_up') and troughs and peaks:
            last_trough = troughs[-1]
            for p in reversed(peaks):
                if p['index'] > last_trough['index']:
                    days = p['index'] - last_trough['index']
                    if days > 0:
                        log_ret = np.log(p['price'] / last_trough['price'])
                        return min(abs(log_ret) / days * 250 * 100, 100)
        elif trend in ('strong_down', 'slow_down') and peaks and troughs:
            last_peak = peaks[-1]
            for t in reversed(troughs):
                if t['index'] > last_peak['index']:
                    days = t['index'] - last_peak['index']
                    if days > 0:
                        log_ret = np.log(last_peak['price'] / t['price'])
                        return min(abs(log_ret) / days * 250 * 100, 100)
        return 0.0

    def _count_persistence(self, turning_points, trend):
        """统计顺应当前趋势的连续同类型转折点对数."""
        if trend == 'sideways':
            return 0
        if trend in ('strong_up', 'slow_up'):
            items = [p for p in turning_points if p['type'] == 'trough']
        else:
            items = [p for p in turning_points if p['type'] == 'peak']

        count = 0
        for i in range(len(items) - 1, 0, -1):
            if trend in ('strong_up', 'slow_up') and items[i]['price'] > items[i-1]['price']:
                count += 1
            elif trend in ('strong_down', 'slow_down') and items[i]['price'] < items[i-1]['price']:
                count += 1
            else:
                break
        return count

    # ── helpers ──────────────────────────────────────────────────────

    def _last_of_type(self, turning_points, tp_type):
        for tp in reversed(turning_points):
            if tp['type'] == tp_type:
                return tp['price']
        return None

    def _empty_result(self):
        return {
            'turning_points': [],
            'trend': 'sideways',
            'strength': {'slope': 0.0, 'persistence': 0, 'score': 0.0},
            'last_high': None,
            'last_low': None,
        }

    def _no_turning_result(self, closes, dates):
        change = (closes[-1] - closes[0]) / closes[0]
        half = self.threshold * 0.5
        if change > half:
            trend = 'slow_up'
        elif change < -half:
            trend = 'slow_down'
        else:
            trend = 'sideways'
        return {
            'turning_points': [],
            'trend': trend,
            'strength': {'slope': 0.0, 'persistence': 0, 'score': 0.0},
            'last_high': float(np.max(closes)),
            'last_low': float(np.min(closes)),
        }
```

- [ ] **Step 4: Run the turning point tests**

```bash
cd C:/Users/cyneuzk/develop/cc_stock && python -m pytest backend/tests/test_trend_analyzer.py::TestTurningPoints -v
```

Expected: 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd C:/Users/cyneuzk/develop/cc_stock && git add backend/strategy_engine/trend_analyzer.py backend/tests/test_trend_analyzer.py && git commit -m "feat: TrendAnalyzer — 之字转向转折点检测"
```

---

### Task 2: Add trend classification + strength tests

**Files:**
- Modify: `backend/tests/test_trend_analyzer.py` (append test classes)

- [ ] **Step 1: Add trend classification tests**

Append to `backend/tests/test_trend_analyzer.py`:

```python
class TestTrendClassification:
    def test_strong_up(self):
        """Higher highs and higher lows = strong_up."""
        # 100→110→105→115 = peaks 110,115  troughs 100,105
        prices = [100, 110, 105, 115, 110, 120]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'strong_up'

    def test_strong_down(self):
        """Lower highs and lower lows = strong_down."""
        prices = [120, 110, 115, 105, 110, 100]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'strong_down'

    def test_slow_up_higher_high_flat_low(self):
        """Higher high but trough not significantly higher = slow_up."""
        # Peak rises ~10%, trough only rises ~1% (<2.5%)
        prices = [100, 110, 101, 111]
        df = make_df(prices)
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df)
        assert result['trend'] == 'slow_up'

    def test_slow_down(self):
        """Lower low but peak not significantly lower = slow_down."""
        prices = [110, 100, 109, 99]
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
        # Multiple higher highs and higher lows
        prices = [100, 108, 103, 112, 107, 118, 113, 125]
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
        if result['trend'] == 'sideways':
            assert result['strength']['persistence'] == 0

    def test_last_high_low(self):
        """Should return the most recent peak and trough prices."""
        prices = [100, 110, 95, 108]
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
        prices = [100, 110, 95, 108]
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
```

- [ ] **Step 2: Run all tests**

```bash
cd C:/Users/cyneuzk/develop/cc_stock && python -m pytest backend/tests/test_trend_analyzer.py -v
```

Expected: all 15 tests PASS

- [ ] **Step 3: Commit**

```bash
cd C:/Users/cyneuzk/develop/cc_stock && git add backend/tests/test_trend_analyzer.py && git commit -m "test: TrendAnalyzer 趋势分类+强度+边界测试"
```

---

### Task 3: Integration — wire into existing strategy

**Files:**
- Modify: `backend/strategy_engine/built_in/trend.py` (use TrendAnalyzer as trend confirmation)

- [ ] **Step 1: Modify trend.py to use TrendAnalyzer for trend confirmation**

Replace the current MA-alignment check with TrendAnalyzer as an additional signal. The strategy keeps its existing MACD + MA logic but adds a TrendAnalyzer-based filter.

Read `backend/strategy_engine/built_in/trend.py` first, then apply this edit:

In the `score` method, after the existing MA alignment scoring, add:

```python
from strategy_engine.trend_analyzer import TrendAnalyzer

# ... inside score() method, after existing calculations:

# TrendAnalyzer confirmation: downgrade if trend structure is weak
ta = TrendAnalyzer(threshold=0.05)
ta_result = ta.analyze(df, lookback=60)
trend_direction = ta_result['trend']

if trend_direction in ('strong_down', 'slow_down'):
    return 0  # downtrend — no matter what MA says

if trend_direction == 'strong_up':
    score = min(score + 10, 100)  # bonus for strong uptrend
elif trend_direction == 'sideways':
    score = score * 0.6  # penalty for unclear trend

return score
```

- [ ] **Step 2: Verify the strategy still works**

Write a quick integration check:

```bash
cd C:/Users/cyneuzk/develop/cc_stock && python -c "
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.strategy_engine.built_in.trend import TrendStrategy

# Generate fake uptrend data
dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(80)]
close = np.linspace(10, 15, 80) + np.random.randn(80) * 0.2
df = pd.DataFrame({
    'date': dates,
    'open': close - 0.1,
    'high': close + 0.3,
    'low': close - 0.3,
    'close': close,
    'volume': np.ones(80) * 1e7,
    'amount': np.ones(80) * 1e8,
    'turnover': np.ones(80) * 2.0,
})

strat = TrendStrategy()
score = strat.score('000001', df)
print(f'Trend strategy score: {score}')
assert 0 <= score <= 100, f'Score {score} out of range'
print('OK')
"
```

- [ ] **Step 3: Commit**

```bash
cd C:/Users/cyneuzk/develop/cc_stock && git add backend/strategy_engine/built_in/trend.py && git commit -m "feat: trend策略集成TrendAnalyzer趋势确认"
```
