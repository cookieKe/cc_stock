import pandas as pd
from backend.strategy_engine.base import BaseStrategy


class ValueStrategy(BaseStrategy):
    name = "value"
    display_name = "价值策略"
    description = "基于PE/PB分位和ROE的基本面价值选股策略"
    parameters = {
        "pe_max": 50,
        "pb_max": 5,
        "roe_min": 8,
    }

    def score(self, code: str, df: pd.DataFrame, financials=None) -> float:
        if financials is None or financials.empty:
            return 50.0
        latest = financials.iloc[0]
        pe = float(latest.get("pe", 0) or 0)
        pb = float(latest.get("pb", 0) or 0)
        roe = float(latest.get("roe", 0) or 0)

        score = 50.0
        if pe > 0 and pe < self.parameters["pe_max"]:
            score += min((1 - pe / self.parameters["pe_max"]) * 30, 30)
        if pb > 0 and pb < self.parameters["pb_max"]:
            score += min((1 - pb / self.parameters["pb_max"]) * 20, 20)
        if roe > self.parameters["roe_min"]:
            score += min((roe - self.parameters["roe_min"]) / 10, 20)
        return round(min(max(score, 0), 100), 2)
