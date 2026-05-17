import os
import json
import numpy as np
import pandas as pd
from backend.strategy_engine.base import BaseStrategy
from backend.api.charts import _calc_kdj


class KDJReversalV2Strategy(BaseStrategy):
    name = "kdj_reversal_v2"
    display_name = "KDJ反转V2.0"
    description = "V2: 数据模板形态匹配 + 底背离 + 回归趋势 + 量能确认 + 反转幅度"

    parameters = {
        "kdj_n": 9,
        "j_threshold": 13,
        "lookback_days": 60,

        # J oversold
        "j_weight": 0.25,

        # Divergence
        "divergence_weight": 0.20,
        "divergence_j_max": 20,
        "divergence_lookback": 60,

        # Trend (regression)
        "trend_weight": 0.15,
        "trend_regression_days": 20,

        # Pattern (data templates)
        "pattern_weight": 0.20,
        "pattern_lookback": 60,
        "pattern_min_corr": 0.3,

        # Volume
        "volume_weight": 0.20,
        "volume_short": 5,
        "volume_long": 20,
        "volume_boost": 1.2,
        "volume_penalty": 0.7,

        # Magnitude multiplier
        "magnitude_lookback": 60,
        "magnitude_max_boost": 1.3,
        "magnitude_min_penalty": 0.7,
    }

    def __init__(self):
        super().__init__()
        self.last_matched_pattern: str | None = None
        self._templates = None

    def _load_templates(self) -> dict:
        if self._templates is not None:
            return self._templates
        self._templates = {}
        d = os.path.join(os.path.dirname(__file__), "..", "patterns_v2")
        if not os.path.isdir(d):
            return self._templates
        for fname in sorted(os.listdir(d)):
            if not fname.endswith(".json"):
                continue
            try:
                with open(os.path.join(d, fname), "r") as f:
                    t = json.load(f)
                curve = np.array(t["curve"], dtype=float)
                if len(curve) >= 5:
                    self._templates[t["name"]] = curve
            except Exception:
                pass
        return self._templates

    def get_required_data(self) -> dict:
        p = self.parameters
        days = max(p["kdj_n"], p["lookback_days"], p["pattern_lookback"],
                   p["divergence_lookback"], p["magnitude_lookback"])
        return {"kline_days": days + 10}

    # ── main scorer ──────────────────────────────────────────────

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        p = self.parameters
        n = p["kdj_n"]
        lookback = p["lookback_days"]

        if len(df) < max(n, lookback) + 5:
            self.last_matched_pattern = None
            return 0.0

        df_tail = df.tail(lookback).copy()
        highs = df_tail["high"].astype(float).tolist()
        lows = df_tail["low"].astype(float).tolist()
        closes = df_tail["close"].astype(float).tolist()

        # ── KDJ hard-gate ──
        k, d, j = _calc_kdj(highs, lows, closes, n)
        j_last = j[-1]
        if j_last is None or j_last >= p["j_threshold"]:
            self.last_matched_pattern = None
            return 0.0

        # ── 1. J oversold ──
        j_score = min((1 - j_last / p["j_threshold"]) * 100, 100)

        # ── 2. Divergence ──
        div_score = self._divergence_score(closes, j, p)

        # ── 3. Trend regression ──
        trend_score = self._trend_regression_score(lows, p)

        # ── 4. Pattern (data templates) ──
        pat_result = self._pattern_score_v2(df, p)
        pattern_score = pat_result["score"]
        self.last_matched_pattern = pat_result["name"]

        # ── 5. Volume confirmation ──
        vol_score = self._volume_score(df, p)

        # ── Weighted sum ──
        w_map = {
            "j": p["j_weight"], "div": p["divergence_weight"],
            "trend": p["trend_weight"], "pat": p["pattern_weight"],
            "vol": p["volume_weight"],
        }
        w_sum = sum(w_map.values())
        if w_sum > 0:
            for k_w in w_map:
                w_map[k_w] /= w_sum

        total = (j_score * w_map["j"] + div_score * w_map["div"]
                 + trend_score * w_map["trend"] + pattern_score * w_map["pat"]
                 + vol_score * w_map["vol"])

        # ── 6. Magnitude multiplier ──
        mag = self._magnitude_factor(df, p)
        total *= mag

        return round(min(max(total, 0), 100), 2)

    # ── 1. J oversold (unchanged from V1) ────────────────────────

    # ── 2. KDJ bottom divergence ─────────────────────────────────

    def _divergence_score(self, closes: list, j_vals: list, p: dict) -> float:
        """检测KDJ底背离: 价格新低但J值反而抬高。"""
        dlookback = p["divergence_lookback"]
        j_max = p["divergence_j_max"]

        closes_arr = np.array(closes[-dlookback:], dtype=float)
        j_arr = np.array(j_vals[-dlookback:], dtype=float)

        # Find troughs in J: local minima below j_max
        j_troughs = []  # list of (index, j_value, close)
        for i in range(1, len(j_arr) - 1):
            if j_arr[i] is not None and not np.isnan(j_arr[i]):
                if j_arr[i] <= j_max and j_arr[i] <= j_arr[i - 1] and j_arr[i] <= j_arr[i + 1]:
                    j_troughs.append((i, float(j_arr[i]), float(closes_arr[i])))

        if len(j_troughs) < 2:
            # Not enough troughs → check if J is in deep oversold as fallback
            if j_vals[-1] is not None and j_vals[-1] <= p["j_threshold"] / 2:
                return 60.0
            return 30.0

        # Take the last two troughs
        t1, t2 = j_troughs[-2], j_troughs[-1]  # t2 = most recent
        _, j1, c1 = t1
        _, j2, c2 = t2

        divergence = (c2 < c1 and j2 > j1)  # price lower, J higher → bullish divergence
        if divergence:
            # Score based on divergence strength
            price_drop = abs(c2 - c1) / c1 if c1 > 0 else 0
            j_rise = abs(j2 - j1) / abs(j1) if j1 != 0 else 0
            strength = min(price_drop * 5 + j_rise * 2, 1.0)
            return round(strength * 100, 2)
        return 20.0

    # ── 3. Trend regression ──────────────────────────────────────

    def _trend_regression_score(self, lows: list, p: dict) -> float:
        """OLS回归求低点趋势斜率，正斜率=低点抬升。"""
        n = p["trend_regression_days"]
        arr = np.array(lows[-n:], dtype=float)
        if len(arr) < n // 2:
            return 50.0

        x = np.arange(len(arr))
        # OLS slope = (Σ(x-x̄)(y-ȳ)) / Σ(x-x̄)²
        x_mean = x.mean()
        y_mean = arr.mean()
        slope = ((x - x_mean) * (arr - y_mean)).sum() / ((x - x_mean) ** 2).sum()

        # Normalize slope relative to price level
        norm_slope = slope / y_mean if y_mean > 0 else 0

        # Map to [0, 100]: 0 slope → 50, strong positive → 100, negative → <50
        score = 50 + norm_slope * 500  # 10% rise over 20 days → +50 points
        return round(min(max(score, 0), 100), 2)

    # ── 4. Pattern matching (data templates) ─────────────────────

    def _pattern_score_v2(self, df: pd.DataFrame, p: dict) -> dict:
        pat_lookback = p.get("pattern_lookback", 60)
        min_corr = p.get("pattern_min_corr", 0.3)
        closes = df["close"].astype(float).tail(pat_lookback).tolist()

        if len(closes) < 10:
            return {"score": 0.0, "name": None}

        templates = self._load_templates()
        if not templates:
            return {"score": 0.0, "name": None}

        prices = np.array(closes, dtype=float)
        p_min, p_max = prices.min(), prices.max()
        if p_max - p_min < 1e-9:
            return {"score": 0.0, "name": None}
        price_norm = (prices - p_min) / (p_max - p_min)

        best_corr = -1.0
        best_name = None
        for name, template in templates.items():
            # Interpolate template to match price length
            if len(template) != len(price_norm):
                xp = np.linspace(0, 1, len(template))
                xi = np.linspace(0, 1, len(price_norm))
                template = np.interp(xi, xp, template)

            corr = float(np.corrcoef(price_norm, template)[0, 1])
            if np.isnan(corr):
                corr = 0.0
            if corr > best_corr:
                best_corr = corr
                best_name = name

        if best_corr < min_corr:
            return {"score": 0.0, "name": None}
        return {"score": round(max(0.0, best_corr) * 100, 2), "name": best_name}

    # ── 5. Volume confirmation ───────────────────────────────────

    def _volume_score(self, df: pd.DataFrame, p: dict) -> float:
        """近期放量→加分，缩量→扣分。"""
        if "volume" not in df.columns or len(df) < p["volume_long"]:
            return 50.0

        vols = df["volume"].astype(float).tolist()
        short_ma = np.mean(vols[-p["volume_short"]:])
        long_ma = np.mean(vols[-p["volume_long"]:])
        if long_ma < 1e-9:
            return 50.0

        ratio = short_ma / long_ma
        if ratio >= p["volume_boost"]:
            return round(min(50 + (ratio - p["volume_boost"]) * 50, 100), 2)
        elif ratio <= p["volume_penalty"]:
            return round(max(50 - (p["volume_penalty"] - ratio) * 100, 0), 2)
        return 50.0

    # ── 6. Magnitude factor ──────────────────────────────────────

    def _magnitude_factor(self, df: pd.DataFrame, p: dict) -> float:
        """反转幅度: 跌得越深 → 潜在空间越大。作为乘数而非加数。"""
        lookback = p["magnitude_lookback"]
        closes = df["close"].astype(float).tail(lookback).tolist()
        if len(closes) < 10:
            return 1.0

        high = max(closes[:-3])   # exclude last 3 to avoid counting the reversal itself
        low = closes[-1]
        if high <= 0 or low <= 0:
            return 1.0

        drop_pct = (high - low) / high  # e.g. 0.30 = 30% drop
        # Normalize: 5% drop → 0.7, 20% drop → 1.3
        factor = 0.7 + drop_pct * 3
        return round(min(max(factor, p["magnitude_min_penalty"]), p["magnitude_max_boost"]), 3)
