import pandas as pd
from backend.strategy_engine.base import BaseStrategy
from backend.api.charts import _calc_kdj


class KDJB2Strategy(BaseStrategy):
    name = "kdj_b2"
    display_name = "KDJ B2买入"
    description = "B2买入信号: J值从B1超卖区拐头向上+长阳放量+J<55+上影线克制"

    parameters = {
        "kdj_n": 9,
        "j_b1_threshold": 13,          # B1区域J值低位阈值
        "j_b2_threshold": 55,          # B2区域J值上限
        "min_pct_change": 4.0,         # 最小涨幅(%)
        "max_upper_shadow_ratio": 0.5, # 最大上影线比例
        "lookback_days": 60,

        # 评分权重
        "j_depth_weight": 0.25,        # J值超卖深度
        "candle_weight": 0.30,         # 阳线强度
        "volume_weight": 0.25,         # 放量质量
        "shadow_weight": 0.20,         # 上影线克制
    }

    def get_required_data(self) -> dict:
        days = max(self.parameters["kdj_n"], self.parameters["lookback_days"], 90)
        return {"kline_days": days + 10}

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        p = self.parameters
        n = p["kdj_n"]
        lookback = p["lookback_days"]

        if len(df) < max(n, lookback) + 5:
            return 0.0

        df_tail = df.tail(lookback).copy()
        highs = df_tail["high"].astype(float).tolist()
        lows = df_tail["low"].astype(float).tolist()
        closes = df_tail["close"].astype(float).tolist()
        opens = df_tail["open"].astype(float).tolist()
        volumes = df_tail["volume"].astype(float).tolist()

        k, d, j = _calc_kdj(highs, lows, closes, n)

        # ── 条件1: 昨日J值低于B1阈值，且最近2日拐头向上 ──
        j_valid = [v for v in j[-5:] if v is not None]
        if len(j_valid) < 5:
            return 0.0

        # J.shift(1) <= B1阈值 (昨日J在超卖区)
        if j_valid[-2] > p["j_b1_threshold"]:
            return 0.0

        # J > J.shift(1) > J.shift(2) (连续2日拐头向上)
        if not (j_valid[-1] > j_valid[-2] > j_valid[-3]):
            return 0.0

        j_last = j_valid[-1]
        j_prev = j_valid[-2]

        # ── 条件2: 今日阳线涨幅 >= min_pct_change ──
        pct_change = (closes[-1] - opens[-1]) / opens[-1] * 100
        if pct_change < p["min_pct_change"]:
            return 0.0

        # ── 条件3: 放量(今日量 > 昨日量) ──
        if volumes[-1] <= volumes[-2]:
            return 0.0

        # ── 条件4: J值 < B2上限 ──
        if j_last >= p["j_b2_threshold"]:
            return 0.0

        # ── 条件5: 上影线比例 ──
        upper_shadow = highs[-1] - max(opens[-1], closes[-1])
        body = abs(closes[-1] - opens[-1])
        upper_shadow_ratio = upper_shadow / (body + 1e-6)
        if upper_shadow_ratio > p["max_upper_shadow_ratio"]:
            return 0.0

        # ── 评分 ──

        # 1. J值超卖深度: 昨日J多低 + 拐头力度
        if j_prev <= 0:
            j_depth_score = 100.0
        else:
            j_depth_score = max(1 - j_prev / p["j_b1_threshold"], 0) * 100

        turn_strength = min((j_last - j_prev) / max(abs(j_prev), 1), 3.0)
        j_score = j_depth_score * 0.6 + turn_strength / 3.0 * 100 * 0.4

        # 2. 阳线强度: 涨幅越大越好，但上影线小加分
        candle_score = min((pct_change - p["min_pct_change"]) / (10 - p["min_pct_change"]) * 100, 100)
        candle_score = max(candle_score, 0)

        # 3. 放量质量: 量比越大越好
        vol_ratio = volumes[-1] / max(volumes[-2], 1e-9)
        if vol_ratio >= 2.0:
            vol_score = 100.0
        elif vol_ratio >= 1.5:
            vol_score = 80.0
        elif vol_ratio >= 1.2:
            vol_score = 60.0
        else:
            vol_score = vol_ratio / 2.0 * 100

        # 4. 上影线克制: 上影线越小越好
        if upper_shadow_ratio <= 0.1:
            shadow_score = 100.0
        elif upper_shadow_ratio <= 0.3:
            shadow_score = 75.0
        else:
            shadow_score = max(1 - upper_shadow_ratio / p["max_upper_shadow_ratio"], 0) * 100

        # ── 加权汇总 ──
        w = {
            "j": p["j_depth_weight"], "candle": p["candle_weight"],
            "vol": p["volume_weight"], "shadow": p["shadow_weight"],
        }
        w_sum = sum(w.values())
        if w_sum > 0:
            for kw in w:
                w[kw] /= w_sum

        total = (j_score * w["j"] + candle_score * w["candle"]
                 + vol_score * w["vol"] + shadow_score * w["shadow"])

        return round(min(max(total, 0), 100), 2)
