import numpy as np
import pandas as pd
from backend.strategy_engine.base import BaseStrategy


class DeepVStrategy(BaseStrategy):
    """深V策略 — 短期+长期双线随机指标 + V底右侧确认。

    昨日短期<=20(深跌) + 昨日长期>=80(大资金未离场) + 今日长期>=90(右侧确认)。
    附加BBI趋势确认。
    """

    name = "deep_v"
    display_name = "深V策略"
    description = "昨日短期深跌+长期高企，今日长期确认走强——V底右侧买入信号"
    parameters = {
        "n1": 3,
        "n2": 21,
        "lookback_days": 80,
        "bbi_periods": [3, 6, 12, 24],
    }

    @staticmethod
    def _line(closes, lows, n):
        """计算单条随机指标线 LINE(N) = 100*(C-LLV(L,N))/(HHV(C,N)-LLV(L,N))"""
        result = [None] * len(closes)
        for i in range(n - 1, len(closes)):
            window_c = closes[i - n + 1:i + 1]
            window_l = lows[i - n + 1:i + 1]
            hh = max(window_c)
            ll = min(window_l)
            denom = hh - ll
            result[i] = (closes[i] - ll) / (denom + 1e-9) * 100 if denom > 0 else 50.0
        return result

    @staticmethod
    def _ma(values, n):
        """简单移动平均，返回与输入等长的列表（前n-1位为None）"""
        s = pd.Series(values)
        ma = s.rolling(n).mean()
        return [None if pd.isna(v) else round(v, 2) for v in ma.tolist()]

    @staticmethod
    def _last_valid(values):
        """获取列表最后一个非None值"""
        for v in reversed(values):
            if v is not None:
                return v
        return None

    @staticmethod
    def _nth_last_valid(values, n=1):
        """获取列表倒数第n个非None值（n=1 即最后一位）。"""
        valid = [v for v in reversed(values) if v is not None]
        if len(valid) >= n:
            return valid[n - 1]
        return None

    def get_required_data(self) -> dict:
        p = self.parameters
        max_n = max(p["n1"], p["n2"], max(p["bbi_periods"]))
        return {"kline_days": max(p["lookback_days"], max_n) + 30}

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        p = self.parameters
        n1 = p["n1"]
        n2 = p["n2"]
        lookback = p["lookback_days"]

        min_rows = max(n1, n2, max(p["bbi_periods"])) + 10
        if len(df) < min_rows:
            return 0.0

        df = df.tail(lookback).copy()
        closes = df["close"].astype(float).tolist()
        lows = df["low"].astype(float).tolist()

        # 1. 计算短期 + 长期随机指标线
        short_line = self._line(closes, lows, n1)
        long_line = self._line(closes, lows, n2)

        # 2. 深V门禁: 昨日短期<=20 AND 昨日长期>=80 AND 今日长期>=90
        yesterday_short = self._nth_last_valid(short_line, 2)
        yesterday_long = self._nth_last_valid(long_line, 2)
        today_long = self._last_valid(long_line)

        if yesterday_short is None or yesterday_long is None or today_long is None:
            return 0.0
        if yesterday_short > 20 or yesterday_long < 80:
            return 0.0
        if today_long < 90:
            return 0.0

        # 3. 计算BBI
        bbi_periods = p["bbi_periods"]
        mas = [self._ma(closes, per) for per in bbi_periods]
        bbi = []
        for i in range(len(closes)):
            vals = [m[i] for m in mas if m[i] is not None]
            bbi.append(sum(vals) / len(vals) if vals else None)

        # 4. 深V核心评分 (用昨日值评估V底深度)
        score = self._signal_deep_v(yesterday_short, yesterday_long)

        # 5. BBI趋势修正 (非上升趋势打五折)
        if not self._bbi_trend(bbi):
            score *= 0.5

        return round(min(max(score, 0), 100), 2)

    def _bbi_trend(self, bbi):
        """检测BBI最近趋势是否向上。取最后10个有效值做线性回归斜率。"""
        valid = [(i, v) for i, v in enumerate(bbi) if v is not None]
        if len(valid) < 5:
            return False
        recent = valid[-10:]
        xs = list(range(len(recent)))
        ys = [v for _, v in recent]
        slope = np.polyfit(xs, ys, 1)[0] if len(xs) >= 3 else 0
        return slope > 0

    @staticmethod
    def _signal_deep_v(yesterday_short, yesterday_long):
        """深V核心评分: 用昨日短期/长期值评估V底深度。
        短期越低分越高 (0分@20 ~ 50分@0)
        长期越高分越高 (0分@80 ~ 50分@100)
        """
        short_score = (1 - yesterday_short / 20) * 50
        long_score = min((yesterday_long - 80) / 20 * 50, 50)
        return min(short_score + long_score, 100)
