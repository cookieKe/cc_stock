import pandas as pd
from backend.data_sources.base import DataSource


_bs_logged_in = False


def _bs_login():
    global _bs_logged_in
    if not _bs_logged_in:
        import baostock as bs
        bs.login()
        _bs_logged_in = True


class BaostockSource(DataSource):
    name = "baostock"
    priority = 1  # fallback after akshare

    def _ensure_login(self):
        _bs_login()

    def is_available(self) -> bool:
        try:
            import baostock
            return True
        except ImportError:
            return False

    def fetch_stock_list(self) -> pd.DataFrame:
        self._ensure_login()
        import baostock as bs
        rs = bs.query_stock_basic()
        rows = []
        while (rs.error_code == "0") & rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=rs.fields)
        df = df.rename(columns={"code": "code", "code_name": "name"})
        df["exchange"] = df["code"].apply(lambda x: "SH" if x.startswith("sh.") else "SZ")
        df["code"] = df["code"].str.replace("sh.", "").str.replace("sz.", "")
        df["industry"] = ""
        df["listed_date"] = pd.to_datetime(df.get("ipoDate", "19700101"), format="%Y-%m-%d", errors="coerce").dt.date
        return df[["code", "name", "exchange", "industry", "listed_date"]]

    def fetch_daily_kline(self, code: str, start_date: str, end_date: str) -> pd.DataFrame:
        self._ensure_login()
        import baostock as bs

        # Convert YYYYMMDD -> YYYY-MM-DD
        if len(start_date) == 8:
            start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        if len(end_date) == 8:
            end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"

        symbol = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        rs = bs.query_history_k_data_plus(
            symbol,
            "date,open,high,low,close,volume,amount,turn",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="1",  # 不复权
        )
        if rs.error_code != "0":
            return pd.DataFrame()

        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows, columns=rs.fields)
        for col in ["open", "high", "low", "close", "volume", "amount", "turn"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df.rename(columns={"turn": "turnover"})[
            ["date", "open", "high", "low", "close", "volume", "amount", "turnover"]
        ]

    def fetch_financials(self, code: str) -> pd.DataFrame:
        self._ensure_login()
        import baostock as bs
        symbol = f"sh.{code}" if code.startswith("6") else f"sz.{code}"
        rs = bs.query_profit_data(code=symbol, year=2025, quarter=4)
        rows = []
        while (rs.error_code == "0") & rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=rs.fields)
        return df

    def fetch_realtime_quote(self, code: str) -> dict:
        return {}

    def fetch_index_kline(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        self._ensure_login()
        import baostock as bs
        if len(start_date) == 8:
            start_date = f"{start_date[:4]}-{start_date[4:6]}-{start_date[6:8]}"
        if len(end_date) == 8:
            end_date = f"{end_date[:4]}-{end_date[4:6]}-{end_date[6:8]}"
        rs = bs.query_history_k_data_plus(
            f"sh.{symbol}",
            "date,open,high,low,close,volume",
            start_date=start_date,
            end_date=end_date,
            frequency="d",
            adjustflag="1",
        )
        if rs.error_code != "0":
            return pd.DataFrame()
        rows = []
        while rs.next():
            rows.append(rs.get_row_data())
        if not rows:
            return pd.DataFrame()
        df = pd.DataFrame(rows, columns=rs.fields)
        for col in ["open", "high", "low", "close", "volume"]:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")
        df["date"] = pd.to_datetime(df["date"]).dt.date
        return df[["date", "open", "high", "low", "close", "volume"]]
