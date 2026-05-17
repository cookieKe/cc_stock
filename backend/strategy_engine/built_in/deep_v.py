import numpy as np
import pandas as pd
from backend.strategy_engine.base import BaseStrategy


class DeepVStrategy(BaseStrategy):
    """深V策略 — 四线随机指标 + 深V形态识别。

    计算4条不同周期的随机指标线（类似Stochastic但使用HHV(C,N)），
    识别"短期洗盘至低位、长期资金维持高位"的深V形态。
    附加BBI趋势确认。
    """

    name = "deep_v"
    display_name = "深V策略"
    description = "四线随机指标+深V形态识别：短期洗盘至低位而长期资金维持高位的底部选股"
    parameters = {
        "n1": 3,
        "n2": 21,
        "four_line_threshold": 6,
        "short_low_threshold": 20,
        "long_high_threshold": 60,
        "long_strong_threshold": 80,
        "golden_cross_long_max": 20,
        "golden_cross_mid_max": 30,
        "lookback_days": 80,
        "bbi_periods": [3, 6, 12, 24],
        "four_zero_weight": 0.20,
        "deep_v_weight": 0.45,
        "cross_red_weight": 0.20,
        "cross_yellow_weight": 0.15,
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
    def _cross_up(line_a, line_b):
        """检测 line_a 是否在最近两有效值处金叉 line_b（上穿）"""
        valid = [(i, a, b) for i, (a, b) in enumerate(zip(line_a, line_b))
                 if a is not None and b is not None]
        if len(valid) < 2:
            return False
        _, prev_a, prev_b = valid[-2]
        _, curr_a, curr_b = valid[-1]
        return prev_a <= prev_b and curr_a > curr_b

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
        highs = df["high"].astype(float).tolist()

        # 1. 计算4条随机指标线
        short_line = self._line(closes, lows, n1)        # 短期 (白线)
        mid_line = self._line(closes, lows, 10)           # 中期 (黄线)
        mid_long_line = self._line(closes, lows, 20)      # 中长期 (紫线)
        long_line = self._line(closes, lows, n2)          # 长期 (红线)

        # 2. 计算BBI
        bbi_periods = p["bbi_periods"]
        mas = [self._ma(closes, per) for per in bbi_periods]
        bbi = []
        for i in range(len(closes)):
            vals = [m[i] for m in mas if m[i] is not None]
            bbi.append(sum(vals) / len(vals) if vals else None)

        # 3. BBI趋势检测
        last_close = closes[-1]
        last_bbi = self._last_valid(bbi)
        bbi_up = self._bbi_trend(bbi)

        # 4. 四个买入信号评分
        signal_four_zero = self._signal_four_zero(short_line, mid_line, mid_long_line, long_line, p)
        signal_deep_v = self._signal_deep_v(short_line, long_line, p)
        signal_cross_red = self._signal_cross_red(short_line, long_line, p)
        signal_cross_yellow = self._signal_cross_yellow(short_line, mid_line, p)

        # 5. 加权汇总
        w = [p["four_zero_weight"], p["deep_v_weight"], p["cross_red_weight"], p["cross_yellow_weight"]]
        w_sum = sum(w)
        if w_sum > 0:
            w = [x / w_sum for x in w]

        total = (signal_four_zero * w[0] + signal_deep_v * w[1]
                 + signal_cross_red * w[2] + signal_cross_yellow * w[3])

        # 6. BBI趋势修正
        if not bbi_up:
            total *= 0.3

        # 7. 长期线强度修正
        last_long = self._last_valid(long_line)
        if last_long is not None and last_long < p["long_strong_threshold"]:
            total *= 0.5

        return round(min(max(total, 0), 100), 2)

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

    def _signal_four_zero(self, short, mid, mid_long, long_line, p):
        """四线归零信号：4条线均≤阈值。"""
        th = p["four_line_threshold"]
        last_short = self._last_valid(short)
        last_mid = self._last_valid(mid)
        last_mid_long = self._last_valid(mid_long)
        last_long = self._last_valid(long_line)
        if all(v is not None for v in [last_short, last_mid, last_mid_long, last_long]):
            if (last_short <= th and last_mid <= th
                    and last_mid_long <= th and last_long <= th):
                return 100.0
        return 0.0

    def _signal_deep_v(self, short, long_line, p):
        """白线下20 + 长期高位信号（核心深V信号）。"""
        last_short = self._last_valid(short)
        last_long = self._last_valid(long_line)
        if last_short is None or last_long is None:
            return 0.0
        if last_short > p["short_low_threshold"]:
            return 0.0
        if last_long < p["long_high_threshold"]:
            return 0.0
        # 短期越低、长期越高 → 分越高
        short_score = (1 - last_short / p["short_low_threshold"]) * 50
        long_score = min((last_long - p["long_high_threshold"])
                         / (100 - p["long_high_threshold"]) * 50, 50)
        return min(short_score + long_score, 100)

    def _signal_cross_red(self, short, long_line, p):
        """白穿红线信号：短期金叉长期 AND 长期 < 阈值。"""
        last_long = self._last_valid(long_line)
        if last_long is None or last_long >= p["golden_cross_long_max"]:
            return 0.0
        if self._cross_up(short, long_line):
            return 100.0
        return 0.0

    def _signal_cross_yellow(self, short, mid, p):
        """白穿黄线信号：短期金叉中期 AND 中期 < 阈值。"""
        last_mid = self._last_valid(mid)
        if last_mid is None or last_mid >= p["golden_cross_mid_max"]:
            return 0.0
        if self._cross_up(short, mid):
            return 100.0
        return 0.0
