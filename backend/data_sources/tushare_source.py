import pandas as pd
from backend.data_sources.base import DataSource
from backend.config import settings


class TushareSource(DataSource):
    name = "tushare"
    priority = 0

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
        df["volume"] = df["volume"] * 100  # Tushare vol is in 手 (100 shares)
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

    def fetch_daily_kline_batch(self, start_date: str, end_date: str) -> pd.DataFrame:
        """批量获取全市场日K线数据。

        使用 Tushare pro.daily(trade_date=...) 不传 ts_code 参数，
        一次请求获取全市场某一天所有股票数据，按交易日循环。
        """
        import time
        from backend.config import settings

        # 1. 获取交易日历
        start = start_date.replace("-", "")
        end = end_date.replace("-", "")
        cal_df = self.pro.trade_cal(exchange="SSE", is_open="1", start_date=start, end_date=end)
        if cal_df.empty:
            return pd.DataFrame()
        trade_dates = sorted(cal_df["cal_date"].tolist())

        # 2. 按交易日循环拉取
        all_frames = []
        delay = settings.tushare_concurrency_delay
        retries = settings.api_retry_count
        backoff = settings.api_retry_backoff

        for trade_date in trade_dates:
            df = None
            for attempt in range(retries):
                try:
                    df = self.pro.daily(trade_date=trade_date)
                    break
                except Exception as e:
                    msg = str(e)
                    if "频率" in msg or "rate" in msg.lower() or "429" in msg:
                        time.sleep(60)  # rate limited, long wait
                    elif attempt < retries - 1:
                        time.sleep(backoff ** attempt)
            if df is None or df.empty:
                continue

            # 3. 转换列名和代码格式
            df = df.rename(columns={
                "trade_date": "date", "open": "open", "high": "high",
                "low": "low", "close": "close", "vol": "volume", "amount": "amount",
            })
            df["volume"] = df["volume"] * 100  # Tushare vol is in 手 (100 shares)
            df["date"] = pd.to_datetime(df["date"], format="%Y%m%d").dt.date
            df["code"] = df["ts_code"].str.replace(".SH", "").str.replace(".SZ", "").str.replace(".BJ", "")
            df["turnover"] = None
            all_frames.append(df[["code", "date", "open", "high", "low", "close", "volume", "amount", "turnover"]])

            time.sleep(delay)

        if not all_frames:
            return pd.DataFrame()
        return pd.concat(all_frames, ignore_index=True)

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
