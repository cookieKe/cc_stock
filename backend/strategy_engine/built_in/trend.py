import numpy as np
import pandas as pd
from backend.strategy_engine.base import BaseStrategy
from backend.strategy_engine.trend_analyzer import TrendAnalyzer


class TrendStrategy(BaseStrategy):
    name = "trend"
    display_name = "趋势跟随策略"
    description = "基于均线多头排列和MACD的趋势选股策略"
    parameters = {
        "ma_short": 5,
        "ma_mid": 20,
        "ma_long": 60,
        "macd_fast": 12,
        "macd_slow": 26,
        "macd_signal": 9,
    }

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        if len(df) < max(self.parameters["ma_long"], self.parameters["macd_slow"]) + 15:
            return 0.0
        close = df["close"].astype(float)
        ma_short = close.rolling(self.parameters["ma_short"]).mean().iloc[-1]
        ma_mid = close.rolling(self.parameters["ma_mid"]).mean().iloc[-1]
        ma_long = close.rolling(self.parameters["ma_long"]).mean().iloc[-1]

        alignment_score = 0
        if ma_short > ma_mid > ma_long:
            alignment_score = 40
        elif ma_short > ma_mid:
            alignment_score = 25
        elif ma_mid > ma_long:
            alignment_score = 10

        ema_fast = close.ewm(span=self.parameters["macd_fast"]).mean()
        ema_slow = close.ewm(span=self.parameters["macd_slow"]).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=self.parameters["macd_signal"]).mean()
        macd_hist = 2 * (dif - dea)

        macd_score = 0
        if dif.iloc[-1] > dea.iloc[-1] and dif.iloc[-1] > 0:
            macd_score = 35
        elif dif.iloc[-1] > dea.iloc[-1]:
            macd_score = 20
        elif dif.iloc[-1] > 0:
            macd_score = 10

        if len(macd_hist) >= 3 and macd_hist.iloc[-1] > macd_hist.iloc[-2] > macd_hist.iloc[-3]:
            macd_score += 10

        price_vs_ma = (close.iloc[-1] - ma_mid) / (ma_mid + 1e-9)
        trend_strength = min(max(price_vs_ma * 200 + 10, 0), 15)

        total = alignment_score + macd_score + trend_strength

        # TrendAnalyzer confirmation: downgrade if trend structure is weak
        ta = TrendAnalyzer(threshold=0.05)
        ta_result = ta.analyze(df, lookback=60)
        trend_direction = ta_result['trend']

        if trend_direction in ('strong_down', 'slow_down'):
            return 0.0  # downtrend — no matter what MA says

        if trend_direction == 'strong_up':
            total = min(total + 10, 100)  # bonus for strong uptrend
        elif trend_direction == 'sideways':
            total = total * 0.6  # penalty for unclear trend

        return round(min(max(total, 0), 100), 2)
