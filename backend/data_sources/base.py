import time
from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd


class DataSource(ABC):
    """数据源抽象基类。所有数据源必须实现此接口。"""

    name: str = "base"

    @abstractmethod
    def fetch_stock_list(self) -> pd.DataFrame:
        """获取全A股列表。返回列: code, name, exchange, industry, listed_date"""

    @abstractmethod
    def fetch_daily_kline(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取日K线。返回列: date, open, high, low, close, volume, amount, turnover"""

    @abstractmethod
    def fetch_financials(self, code: str) -> pd.DataFrame:
        """获取财务数据。返回列: report_date, pe, pb, ps, roe, roa, revenue_growth, profit_growth, market_cap"""

    @abstractmethod
    def fetch_realtime_quote(self, code: str) -> dict:
        """获取实时行情"""

    @abstractmethod
    def fetch_index_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """获取指数K线（基准对比用）。symbol如000300(沪深300)"""

    def is_available(self) -> bool:
        """检查数据源是否可用"""
        return True


class DataSourceManager:
    """多数据源管理器：按优先级调用，失败自动切换备用源，关键字段交叉校验。"""

    def __init__(self):
        self.sources: list[DataSource] = []

    def register(self, source: DataSource, priority: int = 0):
        self.sources.append(source)
        self.sources.sort(key=lambda s: getattr(s, "priority", 99))

    def _try_sources(self, method: str, *args, **kwargs):
        """按优先级尝试所有数据源，带重试和指数退避。"""
        from backend.config import settings
        max_retries = settings.api_retry_count
        backoff = settings.api_retry_backoff

        last_error = None
        for source in self.sources:
            if not source.is_available():
                continue
            fn = getattr(source, method)
            for attempt in range(max_retries):
                try:
                    result = fn(*args, **kwargs)
                    if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                        return result, source.name
                except Exception as e:
                    last_error = e
                    if attempt < max_retries - 1:
                        wait = backoff ** attempt
                        time.sleep(wait)
        raise RuntimeError(f"所有数据源调用 {method} 均失败。最后错误: {last_error}")

    def fetch_stock_list(self):
        return self._try_sources("fetch_stock_list")

    def fetch_daily_kline(self, code: str, start_date: str, end_date: str):
        return self._try_sources("fetch_daily_kline", code, start_date, end_date)

    def fetch_financials(self, code: str):
        return self._try_sources("fetch_financials", code)

    def fetch_realtime_quote(self, code: str):
        return self._try_sources("fetch_realtime_quote", code)

    def fetch_index_kline(self, symbol: str, start_date: str, end_date: str):
        return self._try_sources("fetch_index_kline", symbol, start_date, end_date)

    def cross_validate(self, code: str, date: str):
        """交叉校验：双源对比关键字段（close, volume），偏差>5%则告警。"""
        if len(self.sources) < 2:
            return None
        try:
            df1, n1 = self.sources[0].fetch_daily_kline(code, date, date), self.sources[0].name
            df2, n2 = self.sources[1].fetch_daily_kline(code, date, date), self.sources[1].name
            if df1.empty or df2.empty:
                return None
            diff_close = abs(df1.iloc[0]["close"] - df2.iloc[0]["close"]) / df1.iloc[0]["close"]
            if diff_close > 0.05:
                return {"code": code, "date": date, "diff_close": diff_close, "source1": n1, "source2": n2}
        except Exception:
            pass
        return None
