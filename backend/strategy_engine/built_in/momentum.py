import numpy as np
import pandas as pd
from backend.strategy_engine.base import BaseStrategy


class MomentumStrategy(BaseStrategy):
    name = "momentum"
    display_name = "动量策略"
    description = "基于近期涨幅、量比和换手率的动量选股策略"
    parameters = {
        "lookback_days": 20,
        "volume_ratio_weight": 0.3,
        "return_weight": 0.5,
        "turnover_weight": 0.2,
    }

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        if len(df) < self.parameters["lookback_days"]:
            return 0.0
        df = df.tail(self.parameters["lookback_days"]).copy()
        close = df["close"].astype(float)
        volume = df["volume"].astype(float)
        turnover = df.get("turnover", pd.Series([0] * len(df))).astype(float)

        ret = (close.iloc[-1] - close.iloc[0]) / close.iloc[0]
        ret_score = min(max((ret + 0.1) / 0.3, 0), 1) * 100

        avg_vol_prev = volume.iloc[:-5].mean() if len(volume) >= 10 else volume.mean()
        avg_vol_recent = volume.iloc[-5:].mean() if len(volume) >= 5 else volume.mean()
        vol_ratio = avg_vol_recent / (avg_vol_prev + 1e-9)
        vol_score = min(max((vol_ratio - 0.8) / 1.2, 0), 1) * 100

        avg_turnover = turnover.iloc[-5:].mean()
        turnover_score = min(max(avg_turnover / 5, 0), 1) * 100

        w = self.parameters
        total = ret_score * w["return_weight"] + vol_score * w["volume_ratio_weight"] + turnover_score * w["turnover_weight"]
        return round(min(max(total, 0), 100), 2)
