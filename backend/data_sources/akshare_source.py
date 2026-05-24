import akshare as ak
import pandas as pd
from backend.data_sources.base import DataSource


class AkshareSource(DataSource):
    name = "akshare"
    priority = 0

    def fetch_stock_list(self) -> pd.DataFrame:
        df = ak.stock_info_a_code_name()
        df = df.rename(columns={"code": "code", "name": "name"})
        df["exchange"] = df["code"].apply(lambda x: "SH" if x.startswith("6") else "SZ")
        df["industry"] = ""
        df["listed_date"] = None
        return df[["code", "name", "exchange", "industry", "listed_date"]]

    def fetch_daily_kline(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        symbol = f"sh{code}" if code.startswith("6") else f"sz{code}"
        df = ak.stock_zh_a_daily(symbol=symbol, adjust="")
        if df.empty:
            return df
        df["date"] = pd.to_datetime(df["date"]).dt.date
        start = pd.to_datetime(start_date).date()
        end = pd.to_datetime(end_date).date()
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        numeric_cols = ["open", "high", "low", "close", "volume", "amount", "turnover"]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        cols = [c for c in ["date", "open", "high", "low", "close", "volume", "amount", "turnover"] if c in df.columns]
        return df[cols]

    def fetch_financials(self, code: str) -> pd.DataFrame:
        try:
            df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
            if df.empty:
                return pd.DataFrame()
            df = df.rename(columns={
                "报告日期": "report_date", "市盈率": "pe", "市净率": "pb",
                "净资产收益率": "roe", "总资产报酬率": "roa",
                "营业总收入增长率": "revenue_growth", "归属母公司净利润增长率": "profit_growth",
                "总市值": "market_cap",
            })
            cols = [c for c in ["report_date", "pe", "pb", "roe", "roa", "revenue_growth", "profit_growth", "market_cap"] if c in df.columns]
            df["report_date"] = pd.to_datetime(df["report_date"]).dt.date
            df["ps"] = None
            return df
        except Exception:
            return pd.DataFrame()

    def fetch_realtime_quote(self, code: str) -> dict:
        try:
            df = ak.stock_zh_a_spot()
            row = df[df["代码"] == code]
            if row.empty:
                return {}
            r = row.iloc[0]
            return {
                "code": code,
                "name": str(r.get("名称", "")),
                "price": float(r.get("最新价", 0) or 0),
                "change_pct": float(r.get("涨跌幅", 0) or 0),
                "volume": float(r.get("成交量", 0) or 0),
                "amount": float(r.get("成交额", 0) or 0),
                "high": float(r.get("最高", 0) or 0),
                "low": float(r.get("最低", 0) or 0),
                "open": float(r.get("今开", 0) or 0),
                "pre_close": float(r.get("昨收", 0) or 0),
            }
        except Exception:
            return {}

    def fetch_index_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        try:
            df = ak.stock_zh_index_daily_em(symbol=f"sh{symbol}" if symbol.startswith("000") else f"sz{symbol}")
        except Exception:
            try:
                df = ak.index_zh_a_hist(symbol=symbol, period="daily", start_date=start_date, end_date=end_date)
            except Exception:
                return pd.DataFrame()
        if df.empty:
            return df
        df = df.rename(columns={"date": "date", "open": "open", "high": "high", "low": "low", "close": "close"})
        df["date"] = pd.to_datetime(df["date"]).dt.date
        start = pd.to_datetime(start_date).date()
        end = pd.to_datetime(end_date).date()
        df = df[(df["date"] >= start) & (df["date"] <= end)]
        cols = [c for c in ["date", "open", "high", "low", "close", "volume"] if c in df.columns]
        return df[cols]
