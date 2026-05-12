from abc import ABC, abstractmethod
from typing import List, Optional
import pandas as pd


class BaseStrategy(ABC):
    name: str = "base"
    display_name: str = "基础策略"
    description: str = ""
    parameters: dict = {}
    universe: Optional[List[str]] = None

    @abstractmethod
    def score(self, code: str, df: pd.DataFrame, financials: Optional[pd.DataFrame] = None) -> float:
        """返回 0~100 的评分。df为日K线DataFrame（date,open,high,low,close,volume）。"""

    def get_required_data(self) -> dict:
        """声明所需数据：{"kline_days": 60} 表示需要最近60个交易日K线"""
        return {"kline_days": 60}

    def validate_parameters(self, params: dict) -> dict:
        """校验并合并参数，返回合并后的参数字典"""
        merged = {**self.parameters, **params}
        return merged
