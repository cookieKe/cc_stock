import pandas as pd
from backend.data_sources.base import DataSource
from backend.config import settings


class TushareSource(DataSource):
    name = "tushare"
    priority = 1

    def __init__(self):
        self._pro = None

    @property
    def pro(self):
        if self._pro is None:
            import tushare as ts
            ts.set_token(settings.tushare_token)
            self._pro = ts.pro_api()
        return self._pro

    def is_available(self) -> bool:
        return bool(settings.tushare_token)

    def fetch_stock_list(self) -> pd.DataFrame:
        df = self.pro.stock_basic(exchange="", list_status="L", fields="ts_code,symbol,name,area,industry,list_date")
        if df.empty:
            return df
        df["exchange"] = df["ts_code"].str.split(".").str[1]
        df["listed_date"] = pd.to_datetime(df["list_date"], format="%Y%m%d").dt.date
        return df.rename(columns={"symbol": "code"})[["code", "name", "exchange", "industry", "listed_date"]]

    def fetch_daily_kline(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        df = self.pro.daily(ts_code=ts_code, start_date=start, end_date=end)
        if df.empty:
            return df
        df = df.rename(columns={
            "trade_date": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "vol": "volume", "amount": "amount",
        })
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.date
        df["turnover"] = None
        return df[["date", "open", "high", "low", "close", "volume", "amount", "turnover"]]

    def fetch_financials(self, code: str) -> pd.DataFrame:
        ts_code = f"{code}.SH" if code.startswith("6") else f"{code}.SZ"
        df = self.pro.fina_indicator(ts_code=ts_code)
        if df.empty:
            return df
        df = df.rename(columns={
            "end_date": "report_date", "pe": "pe", "pb": "pb",
            "roe": "roe", "roa": "roa",
        })
        df["report_date"] = pd.to_datetime(df["report_date"], format="%Y%m%d").dt.date
        return df

    def fetch_realtime_quote(self, code: str) -> dict:
        return {}

    def fetch_index_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        df = self.pro.index_daily(ts_code=f"{symbol}.SH", start_date=start, end_date=end)
        if df.empty:
            return df
        df = df.rename(columns={
            "trade_date": "date", "open": "open", "high": "high",
            "low": "low", "close": "close", "vol": "volume",
        })
        df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.date
        return df[["date", "open", "high", "low", "close", "volume"]]
