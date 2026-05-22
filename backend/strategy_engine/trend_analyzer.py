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
        strength = self._calc_strength(turning_points, trend)
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
        # 反转: 最新->最早
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
                # 向后看价格上升 -> 跟踪最高点
                if price > extreme_price:
                    extreme_price = price
                    extreme_idx = i
                # 从最高点回落超过阈值 -> 峰值
                if (extreme_price - price) / extreme_price >= self.threshold:
                    turning_rev.append(self._make_tp('peak', extreme_price, extreme_idx, dates, n))
                    direction = 'down'
                    extreme_price = price
                    extreme_idx = i
            else:
                # 向后看价格下降 -> 跟踪最低点
                if price < extreme_price:
                    extreme_price = price
                    extreme_idx = i
                # 从最低点反弹超过阈值 -> 谷底
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

    def _calc_strength(self, turning_points, trend):
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
