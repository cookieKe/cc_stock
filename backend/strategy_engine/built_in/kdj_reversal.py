import pandas as pd
from backend.strategy_engine.base import BaseStrategy
from backend.strategy_engine.pattern_loader import get_pattern_loader
from backend.api.charts import _calc_kdj


class KDJReversalStrategy(BaseStrategy):
    name = "kdj_reversal"
    display_name = "KDJ反转策略"
    description = "基于KDJ超卖+价格结构反转+形态相似度的底部选股策略"
    parameters = {
        "kdj_n": 9,
        "j_threshold": 13,
        "lookback_days": 60,
        "segments": 3,
        "j_weight": 0.40,
        "low_weight": 0.20,
        "high_weight": 0.20,
        "pattern_weight": 0.20,
        "pattern_lookback": 60,
        "pattern_min_corr": 0.3,
    }

    def __init__(self):
        super().__init__()
        self.last_matched_pattern: str | None = None

    def get_required_data(self) -> dict:
        p = self.parameters
        return {"kline_days": max(p["kdj_n"], p["lookback_days"], p.get("pattern_lookback", 60)) + 10}

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        p = self.parameters
        n = p["kdj_n"]
        lookback = p["lookback_days"]
        segments = p["segments"]

        if len(df) < max(n, lookback) + 5:
            self.last_matched_pattern = None
            return 0.0

        df_tail = df.tail(lookback).copy()
        highs = df_tail["high"].astype(float).tolist()
        lows = df_tail["low"].astype(float).tolist()
        closes = df_tail["close"].astype(float).tolist()

        # KDJ
        k, d, j = _calc_kdj(highs, lows, closes, n)
        j_last = j[-1]
        if j_last is None:
            self.last_matched_pattern = None
            return 0.0

        # J score: below threshold, the lower J the higher the score.
        # If J is not in oversold zone, the stock fails this strategy entirely.
        threshold = p["j_threshold"]
        if j_last >= threshold:
            self.last_matched_pattern = None
            return 0.0
        j_score = min((1 - j_last / threshold) * 100, 100)

        # Higher lows score
        low_score = self._trend_score(lows, segments, is_high=False)

        # Higher highs score
        high_score = self._trend_score(highs, segments, is_high=True)

        # Pattern similarity score
        pat_result = self._pattern_score(df)
        pattern_score = pat_result["score"]
        self.last_matched_pattern = pat_result["name"]

        # Normalize weights to sum to 1.0 (handles DB param drift)
        w_j = p["j_weight"]
        w_l = p["low_weight"]
        w_h = p["high_weight"]
        w_p = p.get("pattern_weight", 0.20)
        w_sum = w_j + w_l + w_h + w_p
        if w_sum > 0:
            w_j, w_l, w_h, w_p = w_j / w_sum, w_l / w_sum, w_h / w_sum, w_p / w_sum

        total = j_score * w_j + low_score * w_l + high_score * w_h + pattern_score * w_p
        return round(min(max(total, 0), 100), 2)

    def _pattern_score(self, df: pd.DataFrame) -> dict:
        p = self.parameters
        pat_lookback = p.get("pattern_lookback", 60)
        min_corr = p.get("pattern_min_corr", 0.3)
        closes = df["close"].astype(float).tail(pat_lookback).tolist()
        if len(closes) < 10:
            return {"score": 0.0, "name": None}
        loader = get_pattern_loader()
        return loader.match_with_info(closes, min_correlation=min_corr)

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
