import pandas as pd
from backend.strategy_engine.base import BaseStrategy
from backend.api.charts import _calc_kdj


class KDJReversalStrategy(BaseStrategy):
    name = "kdj_reversal"
    display_name = "KDJ反转策略"
    description = "基于KDJ超卖+价格结构反转（低点抬高、高点抬高）的底部选股策略"
    parameters = {
        "kdj_n": 9,
        "j_threshold": 13,
        "lookback_days": 60,
        "segments": 3,
        "j_weight": 0.5,
        "low_weight": 0.25,
        "high_weight": 0.25,
    }

    def get_required_data(self) -> dict:
        return {"kline_days": max(self.parameters["kdj_n"], self.parameters["lookback_days"]) + 10}

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        p = self.parameters
        n = p["kdj_n"]
        lookback = p["lookback_days"]
        segments = p["segments"]

        if len(df) < max(n, lookback) + 5:
            return 0.0

        df_tail = df.tail(lookback).copy()
        highs = df_tail["high"].astype(float).tolist()
        lows = df_tail["low"].astype(float).tolist()
        closes = df_tail["close"].astype(float).tolist()

        # KDJ
        k, d, j = _calc_kdj(highs, lows, closes, n)
        j_last = j[-1]
        if j_last is None:
            return 0.0

        # J score: below threshold, the lower J the higher the score.
        # If J is not in oversold zone, the stock fails this strategy entirely.
        threshold = p["j_threshold"]
        if j_last >= threshold:
            return 0.0
        j_score = min((1 - j_last / threshold) * 100, 100)

        # Higher lows score
        low_score = self._trend_score(lows, segments, is_high=False)

        # Higher highs score
        high_score = self._trend_score(highs, segments, is_high=True)

        total = j_score * p["j_weight"] + low_score * p["low_weight"] + high_score * p["high_weight"]
        return round(min(max(total, 0), 100), 2)

    def _trend_score(self, values: list, segments: int, is_high: bool) -> float:
        """检查分段极值是否逐步抬高。is_high=True取max否则取min。"""
        n = len(values)
        seg_size = max(n // segments, 5)
        if seg_size < 3:
            return 50.0

        extrema = []
        for i in range(segments):
            start = n - seg_size * (segments - i)
            end = n - seg_size * (segments - i - 1)
            start = max(start, 0)
            seg = values[start:end]
            if not seg:
                continue
            extrema.append(max(seg) if is_high else min(seg))

        if len(extrema) < 2:
            return 50.0

        up_count = sum(1 for k in range(1, len(extrema)) if extrema[k] > extrema[k - 1])
        ratio = up_count / (len(extrema) - 1)
        return round(ratio * 100, 2)
