import os
import json
import numpy as np
import pandas as pd
from backend.strategy_engine.base import BaseStrategy
from backend.strategy_engine.trend_analyzer import TrendAnalyzer
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

        # Trend (TrendAnalyzer)
        "trend_weight": 0.15,

        # Pattern (data templates)
        "pattern_weight": 0.20,
        "pattern_lookback": 60,
        "pattern_min_corr": 0.3,

        # Volume (structure)
        "volume_weight": 0.20,

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
                with open(os.path.join(d, fname), "r", encoding="utf-8") as f:
                    t = json.load(f)
                curve = np.array(t["curve"], dtype=float)
                if len(curve) >= 5:
                    entry = {"curve": curve}
                    if "volume_curve" in t:
                        entry["volume_curve"] = np.array(t["volume_curve"], dtype=float)
                    self._templates[t["name"]] = entry
            except Exception:
                pass
        return self._templates

    def get_required_data(self) -> dict:
        p = self.parameters
        days = max(p["kdj_n"], p["lookback_days"], p["pattern_lookback"],
                   p["divergence_lookback"], p["magnitude_lookback"], 120)
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

        # ── Volume structure hard-gate: 峰值量须高于下跌段均量 ──
        if not self._pass_volume_structure_gate(df, p):
            self.last_matched_pattern = None
            return 0.0

        # ── 1. J oversold ──
        j_score = min((1 - j_last / p["j_threshold"]) * 100, 100)

        # ── 2. Divergence ──
        div_score = self._divergence_score(closes, j, p)

        # ── 3. Trend (TrendAnalyzer) ──
        trend_score = self._trend_analyzer_score(df, p)

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

        # ── 7. 知行多空乘数 ──
        total *= self._zhixng_multiplier(df, p)

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

    def _trend_analyzer_score(self, df: pd.DataFrame, p: dict) -> float:
        """用TrendAnalyzer之字转向判断趋势结构并映射到0-100。"""
        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(df, lookback=p["lookback_days"])
        trend = result["trend"]
        strength = result["strength"]["score"]
        tps = result["turning_points"]

        base = {
            "strong_up": 80, "slow_up": 60, "sideways": 45,
            "slow_down": 25, "strong_down": 10,
        }.get(trend, 45)

        ratio = {
            "strong_up": 0.20, "slow_up": 0.25, "sideways": 0.15,
            "slow_down": 0.20, "strong_down": 0.10,
        }.get(trend, 0.15)

        score = base + strength * ratio

        if tps and tps[-1]["type"] == "trough":
            score += 10

        return round(min(max(score, 0), 100), 2)

    # ── 4. Pattern matching (data templates) ─────────────────────

    def _pattern_score_v2(self, df: pd.DataFrame, p: dict) -> dict:
        pat_lookback = p.get("pattern_lookback", 60)
        min_corr = p.get("pattern_min_corr", 0.3)
        tail_df = df.tail(pat_lookback)
        closes = tail_df["close"].astype(float).tolist()

        if len(closes) < 10:
            return {"score": 0.0, "name": None}

        templates = self._load_templates()
        if not templates:
            return {"score": 0.0, "name": None}

        # 价格归一化
        prices = np.array(closes, dtype=float)
        p_min, p_max = prices.min(), prices.max()
        if p_max - p_min < 1e-9:
            return {"score": 0.0, "name": None}
        price_norm = (prices - p_min) / (p_max - p_min)

        # 成交量归一化
        volume_norm = None
        if "volume" in tail_df.columns:
            vols = tail_df["volume"].astype(float).values
            v_min, v_max = vols.min(), vols.max()
            if v_max - v_min > 1e-9:
                volume_norm = (vols - v_min) / (v_max - v_min)

        best_combined = -1.0
        best_name = None
        for name, tmpl in templates.items():
            t_curve = tmpl["curve"]
            if len(t_curve) != len(price_norm):
                xp = np.linspace(0, 1, len(t_curve))
                xi = np.linspace(0, 1, len(price_norm))
                t_curve = np.interp(xi, xp, t_curve)

            price_corr = float(np.corrcoef(price_norm, t_curve)[0, 1])
            if np.isnan(price_corr):
                price_corr = 0.0

            # 成交量相关系数
            if volume_norm is not None and "volume_curve" in tmpl:
                t_vol = tmpl["volume_curve"]
                if len(t_vol) != len(volume_norm):
                    xp = np.linspace(0, 1, len(t_vol))
                    xi = np.linspace(0, 1, len(volume_norm))
                    t_vol = np.interp(xi, xp, t_vol)
                vol_corr = float(np.corrcoef(volume_norm, t_vol)[0, 1])
                if np.isnan(vol_corr):
                    vol_corr = 0.0
                combined = price_corr * 0.6 + vol_corr * 0.4
            else:
                combined = price_corr

            if combined > best_combined:
                best_combined = combined
                best_name = name

        if best_combined < min_corr:
            return {"score": 0.0, "name": None}
        return {"score": round(max(0.0, best_combined) * 100, 2), "name": best_name}

    # ── 5. Volume confirmation ───────────────────────────────────

    def _pass_volume_structure_gate(self, df: pd.DataFrame, p: dict) -> bool:
        """峰值量须高于下跌段均量，否则过滤(抛压未在高点释放)。"""
        if "volume" not in df.columns:
            return True

        lookback = p["lookback_days"]
        tail = df.tail(lookback).copy()

        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(tail)
        tps = result["turning_points"]

        peaks = [tp for tp in tps if tp["type"] == "peak"]
        troughs = [tp for tp in tps if tp["type"] == "trough"]
        if not peaks:
            return True

        last_peak = peaks[-1]
        subsequent_trough = None
        for t in troughs:
            if t["index"] > last_peak["index"]:
                subsequent_trough = t
                break

        pi = last_peak["index"]
        ti = subsequent_trough["index"] if subsequent_trough else len(tail) - 1
        if ti - pi < 2:
            return True

        peak_vol = float(tail["volume"].iloc[pi])
        decline_vols = tail["volume"].iloc[pi + 1 : ti + 1].astype(float)
        max_decline_vol = decline_vols.max()
        avg_decline_vol = decline_vols.mean()
        if avg_decline_vol < 1e-9:
            return True

        # 峰值量须为整个下跌段的最大量(不允许后续某天量更大)
        if peak_vol <= max_decline_vol:
            return False
        # 峰值量须至少比下跌均量高5%
        return peak_vol / avg_decline_vol >= 1.05

    def _volume_score(self, df: pd.DataFrame, p: dict) -> float:
        """基于TrendAnalyzer转折点的量能结构分析: 峰值放量+下跌缩量。"""
        if "volume" not in df.columns:
            return 50.0

        lookback = p["lookback_days"]
        tail = df.tail(lookback).copy()

        ta = TrendAnalyzer(threshold=0.05)
        result = ta.analyze(tail)
        tps = result["turning_points"]

        if len(tps) < 2:
            return 50.0

        peaks = [tp for tp in tps if tp["type"] == "peak"]
        troughs = [tp for tp in tps if tp["type"] == "trough"]
        if not peaks or not troughs:
            return 50.0

        last_peak = peaks[-1]

        subsequent_trough = None
        for t in troughs:
            if t["index"] > last_peak["index"]:
                subsequent_trough = t
                break
        if subsequent_trough is None:
            # 尚未确认谷底 → 分析 peak 至今的下跌段
            ti = len(tail) - 1
        else:
            ti = subsequent_trough["index"]

        pi = last_peak["index"]
        if ti - pi < 2:
            return 50.0

        peak_vol = float(tail["volume"].iloc[pi])
        decline_vols = tail["volume"].iloc[pi + 1 : ti + 1].astype(float)
        decline_closes = tail["close"].iloc[pi + 1 : ti + 1].astype(float)

        avg_decline_vol = decline_vols.mean()
        if avg_decline_vol < 1e-9:
            return 50.0

        # 条件1已在_pass_volume_structure_gate中作为硬门禁检查
        # 此处只评估条件2: 下跌缩量比例
        down_days = 0
        contraction_days = 0
        for i in range(1, len(decline_closes)):
            if decline_closes.iloc[i] < decline_closes.iloc[i - 1]:
                down_days += 1
                if decline_vols.iloc[i] < decline_vols.iloc[i - 1]:
                    contraction_days += 1

        if down_days == 0:
            return 50.0

        contraction_pct = contraction_days / down_days
        if contraction_pct >= 0.7:
            score = 100.0
        elif contraction_pct >= 0.5:
            score = 70.0
        else:
            score = contraction_pct * 140.0

        return round(min(max(score, 0), 100), 2)

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

    # ── 7. 知行多空乘数 ─────────────────────────────────────────

    def _zhixng_multiplier(self, df: pd.DataFrame, p: dict) -> float:
        """收盘价 vs BBI 位置决定折扣: >=BBI→1.0, >=95%→0.8, >=90%→0.5, <90%→0.2。"""
        closes = df["close"].astype(float)
        if len(closes) < 114:
            return 1.0

        s = pd.Series(closes)
        ma14 = s.rolling(14).mean()
        ma28 = s.rolling(28).mean()
        ma57 = s.rolling(57).mean()
        ma114 = s.rolling(114).mean()

        vals = [m.iloc[-1] for m in [ma14, ma28, ma57, ma114] if not pd.isna(m.iloc[-1])]
        if not vals:
            return 1.0

        bbi = sum(vals) / len(vals)
        ratio = closes.iloc[-1] / bbi
        if ratio >= 1.0:
            return 1.0
        elif ratio >= 0.95:
            return 0.8
        elif ratio >= 0.90:
            return 0.5
        else:
            return 0.2
