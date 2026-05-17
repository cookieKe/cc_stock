import threading
from datetime import date, timedelta, datetime, time

import pandas as pd
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models.stock import Stock
from backend.models.market_data import MarketData
from backend.models.financials import Financials
from backend.models.scan_result import ScanResult
from backend.models.watchlist import Watchlist
from backend.models.backtest import Backtest
from backend.models.notification import Notification
from backend.models.strategy import Strategy
from backend.services.data_sync import get_last_trade_date

router = APIRouter(prefix="/api/stats", tags=["stats"])

_CACHE_VERSION = 2  # 递增此版本号使所有旧缓存自动失效
_market_cache = {"data": None, "trade_date": None, "cache_until": None, "version": 0}
_market_cache_lock = threading.Lock()


@router.get("/data-status")
def get_data_status(db: Session = Depends(get_db)):
    """轻量数据状态：最新交易日、股票总数、扫描状态。"""
    stock_total = db.query(func.count(Stock.id)).scalar()
    stock_active = db.query(func.count(Stock.id)).filter(Stock.is_active == True).scalar()
    kline_total = db.query(func.count(MarketData.id)).scalar()
    kline_stocks = db.query(func.count(func.distinct(MarketData.stock_code))).scalar()
    last_trade = get_last_trade_date(db)
    latest_scan = db.query(func.max(ScanResult.scan_date)).scalar()
    scan_today = None
    if latest_scan:
        from datetime import date
        scan_today = str(latest_scan) == str(date.today())

    return {
        "stock_total": stock_total,
        "stock_active": stock_active,
        "kline_total": kline_total,
        "kline_stocks": kline_stocks,
        "last_trade_date": str(last_trade) if last_trade else None,
        "latest_scan_date": str(latest_scan) if latest_scan else None,
        "scan_today": scan_today,
    }


@router.get("/summary")
def get_data_summary(db: Session = Depends(get_db)):
    stock_count = db.query(func.count(Stock.id)).scalar()
    active_count = db.query(func.count(Stock.id)).filter(Stock.is_active == True).scalar()  # noqa: E712

    kline_count = db.query(func.count(MarketData.id)).scalar()
    kline_stocks = db.query(func.count(func.distinct(MarketData.stock_code))).scalar()
    kline_start = db.query(func.min(MarketData.trade_date)).scalar()
    kline_end = db.query(func.max(MarketData.trade_date)).scalar()

    fin_count = db.query(func.count(Financials.id)).scalar()
    fin_stocks = db.query(func.count(func.distinct(Financials.stock_code))).scalar()

    scan_count = db.query(func.count(ScanResult.id)).scalar()
    scan_dates = db.query(func.count(func.distinct(ScanResult.scan_date))).scalar()
    latest_scan = db.query(func.max(ScanResult.scan_date)).scalar()

    wl_count = db.query(func.count(Watchlist.id)).filter(Watchlist.is_active == True).scalar()  # noqa: E712
    wl_total = db.query(func.count(Watchlist.id)).scalar()

    bt_count = db.query(func.count(Backtest.id)).scalar()
    strategy_count = db.query(func.count(Strategy.id)).filter(Strategy.is_enabled == True).scalar()  # noqa: E712

    notif_count = db.query(func.count(Notification.id)).scalar()
    unread = db.query(func.count(Notification.id)).filter(Notification.is_read == False).scalar()  # noqa: E712

    # Per-exchange breakdown
    exchange_stats = (
        db.query(Stock.exchange, func.count(Stock.id))
        .filter(Stock.is_active == True)
        .group_by(Stock.exchange)
        .all()
    )

    # Scan history
    recent_scans = (
        db.query(
            ScanResult.scan_date,
            func.count(func.distinct(ScanResult.stock_code)).label("stocks"),
            func.count(ScanResult.id).label("records"),
        )
        .group_by(ScanResult.scan_date)
        .order_by(ScanResult.scan_date.desc())
        .limit(10)
        .all()
    )

    # K-line coverage per stock (top stocks with most data)
    top_kline = (
        db.query(
            MarketData.stock_code,
            func.count(MarketData.id).label("cnt"),
            func.min(MarketData.trade_date).label("first"),
            func.max(MarketData.trade_date).label("last"),
        )
        .group_by(MarketData.stock_code)
        .order_by(func.count(MarketData.id).desc())
        .limit(30)
        .all()
    )

    return {
        "stocks": {
            "total": stock_count,
            "active": active_count,
            "exchanges": [{"exchange": e, "count": c} for e, c in exchange_stats],
        },
        "klines": {
            "total_records": kline_count,
            "stocks_with_data": kline_stocks,
            "date_start": str(kline_start) if kline_start else None,
            "date_end": str(kline_end) if kline_end else None,
            "top_coverage": [
                {"code": r[0], "records": r[1], "first": str(r[2]) if r[2] else None, "last": str(r[3]) if r[3] else None}
                for r in top_kline
            ],
        },
        "financials": {
            "total_records": fin_count,
            "stocks_with_data": fin_stocks,
        },
        "scans": {
            "total_records": scan_count,
            "scan_count": scan_dates,
            "latest": str(latest_scan) if latest_scan else None,
            "recent": [
                {"date": str(r[0]), "stocks": r[1], "records": r[2]}
                for r in recent_scans
            ],
        },
        "watchlist": {
            "active": wl_count,
            "total": wl_total,
        },
        "backtests": {
            "total": bt_count,
            "enabled_strategies": strategy_count,
        },
        "notifications": {
            "total": notif_count,
            "unread": unread,
        },
    }


def _find_next_trade_date(db: Session, current: date) -> date:
    next_date = (
        db.query(func.min(MarketData.trade_date))
        .filter(MarketData.trade_date > current)
        .scalar()
    )
    if next_date:
        return next_date
    d = current + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _in_cache_window(now: datetime, trade_date: date, cache_until: datetime) -> bool:
    start = datetime.combine(trade_date, time(16, 0))
    return start <= now <= cache_until


@router.get("/market-overview")
def get_market_overview(db: Session = Depends(get_db)):
    """A股整体趋势 + 活跃市值。缓存窗口: [交易日16:00, 下一交易日09:00]。"""
    now = datetime.now()
    latest_trade_date = db.query(func.max(MarketData.trade_date)).scalar()

    with _market_cache_lock:
        if (_market_cache["data"] is not None
                and _market_cache["version"] == _CACHE_VERSION
                and _market_cache["trade_date"] == latest_trade_date
                and _market_cache["cache_until"] is not None):
            if _in_cache_window(now, _market_cache["trade_date"], _market_cache["cache_until"]):
                resp = dict(_market_cache["data"])
                resp["cached"] = True
                return resp

    data = _compute_market_overview(db, latest_trade_date)

    if latest_trade_date:
        cache_until = datetime.combine(
            _find_next_trade_date(db, latest_trade_date), time(9, 0)
        )
        with _market_cache_lock:
            _market_cache["data"] = data
            _market_cache["trade_date"] = latest_trade_date
            _market_cache["cache_until"] = cache_until
            _market_cache["version"] = _CACHE_VERSION

    data["cached"] = False
    return data


def _fetch_one_index(symbol: str, name: str, start_str: str, end_str: str) -> dict:
    info = {"name": name, "code": symbol, "latest": None, "change_pct": None,
            "dates": [], "closes": []}
    try:
        import akshare as ak

        # 深证用 sz 前缀，上证用 sh 前缀
        prefix = "sh" if symbol.startswith("000") else "sz"
        em_symbol = f"{prefix}{symbol}"

        df = None
        for try_symbol in [em_symbol, symbol]:
            try:
                df = ak.stock_zh_index_daily_em(symbol=try_symbol)
                if df is not None and not df.empty:
                    break
            except Exception:
                continue
        if df is None or df.empty:
            return info

        # 统一列名
        if "date" not in df.columns:
            return info
        df["date"] = pd.to_datetime(df["date"]).dt.date

        if not df.empty and len(df) >= 2:
            df = df.sort_values("date")
            info["dates"] = [str(d) for d in df["date"].tolist()]
            closes = df["close"].tolist()
            info["closes"] = [round(float(c), 2) for c in closes]
            info["latest"] = round(float(closes[-1]), 2)
            prev = float(closes[-2])
            if prev > 0:
                info["change_pct"] = round((float(closes[-1]) - prev) / prev * 100, 2)
    except Exception:
        pass
    return info


def _compute_market_overview(db: Session, latest_trade_date) -> dict:
    today_str = str(date.today())
    start_str = str(date.today() - timedelta(days=180))

    sh_index = _fetch_one_index("000001", "上证指数", start_str, today_str)
    sz_index = _fetch_one_index("399001", "深证成指", start_str, today_str)

    # 活跃市值 OAMV: 从通达信直接获取活筹指数 880855
    active_cap = _fetch_oamv_tdx()

    # 总市值最新值 + 历史趋势线
    total_cap = _fetch_total_cap_with_history(db, latest_trade_date)

    return {
        "indices": [sh_index, sz_index],
        "active_market_cap": active_cap,
        "total_market_cap": total_cap,
        "trade_date": str(latest_trade_date) if latest_trade_date else None,
    }


def _oamv_from_tdx(df) -> dict:
    """把通达信返回的 OHLCV DataFrame 转成 sparkline 格式。"""
    result = {"name": "活跃市值(0AMV)", "latest": None, "change_pct": None,
              "dates": [], "values": []}
    if df is None or df.empty or len(df) < 2:
        return result
    try:
        dates_raw = df["date"] if "date" in df.columns else df.index
        closes = df["close"]
        result["dates"] = [str(d) for d in dates_raw]
        result["values"] = [round(float(c), 2) for c in closes]
        latest = float(closes.iloc[-1])
        prev = float(closes.iloc[-2])
        result["latest"] = round(latest, 2)
        if prev > 0:
            result["change_pct"] = round((latest - prev) / prev * 100, 2)
    except Exception:
        pass
    return result


def _fetch_oamv_tdx() -> dict:
    """从通达信获取活筹指数 880855。失败则返回空结构。"""
    empty = {"name": "活跃市值(0AMV)", "latest": None, "change_pct": None,
             "dates": [], "values": []}
    try:
        import akshare as ak
        # 试多种可能的函数名和参数格式
        df = None
        for fn_name in ["stock_zh_index_daily_tx", "index_zh_a_hist"]:
            try:
                fn = getattr(ak, fn_name, None)
                if fn is None:
                    continue
                if fn_name == "index_zh_a_hist":
                    df = fn(symbol="880855", period="daily",
                            start_date="20100101", end_date=str(date.today()))
                else:
                    df = fn(symbol="880855")
                if df is not None and not df.empty:
                    break
            except Exception:
                continue
        if df is not None and not df.empty:
            # 统一列名为英文
            rename_map = {
                "日期": "date", "开盘": "open", "最高": "high",
                "最低": "low", "收盘": "close", "成交量": "volume", "成交额": "amount",
            }
            df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns})
            return _oamv_from_tdx(df)
    except Exception:
        pass
    return empty


def _fetch_total_cap_with_history(db: Session, latest_trade_date) -> dict:
    """总市值: 最新值从 SSE+SZSE 汇总获取，历史趋势用全A收盘价加权估算。"""
    result = {"name": "总市值", "latest": None, "change_pct": None,
              "dates": [], "values": []}

    # 1. 最新总市值：SSE + SZSE 汇总
    total_cap = None
    try:
        import akshare as ak
        sse = ak.stock_sse_summary()
        szse = ak.stock_szse_summary(date=str(date.today()))
        sse_cap = _parse_sse_cap(sse)
        szse_cap = _parse_szse_cap(szse)
        if sse_cap and szse_cap:
            total_cap = int(sse_cap + szse_cap)
    except Exception:
        pass

    # 2. 历史趋势线：全A股 SUM(close) 近似替代总市值趋势
    if latest_trade_date:
        start = latest_trade_date - timedelta(days=200)
        rows = (
            db.query(
                MarketData.trade_date,
                func.sum(MarketData.close).label("sum_close"),
            )
            .filter(
                MarketData.trade_date >= start,
                MarketData.trade_date <= latest_trade_date,
            )
            .group_by(MarketData.trade_date)
            .order_by(MarketData.trade_date)
            .all()
        )
        if rows and total_cap:
            # 以最新日的 sum_close 为锚点，缩放至总市值
            latest_sum = float(rows[-1].sum_close) if rows[-1].sum_close else 1
            scale = total_cap / latest_sum if latest_sum > 0 else 1
            result["dates"] = [str(r.trade_date) for r in rows]
            result["values"] = [round(float(r.sum_close) * scale, 2) for r in rows]

    if total_cap:
        result["latest"] = total_cap
    if len(result["values"]) >= 2:
        vals = result["values"]
        last = vals[-1]
        prev = vals[-2]
        if prev and prev != 0:
            result["change_pct"] = round((last - prev) / prev * 100, 2)
    return result


def _parse_sse_cap(df) -> float | None:
    """从上交所 summary DataFrame 提取股票合计总市值（亿元）。"""
    try:
        if df is None or df.empty:
            return None
        stock_row = df[df["项目"] == "股票"]
        if stock_row.empty:
            stock_row = df[df.iloc[:, 0].str.contains("股票", na=False)]
        if stock_row.empty:
            return None
        col = "总市值" if "总市值" in df.columns else df.columns[1]
        val = stock_row.iloc[0][col]
        return float(val) * 1e8  # SSE 返回的是亿元
    except Exception:
        return None


def _parse_szse_cap(df) -> float | None:
    """从深交所 summary DataFrame 提取股票合计总市值（元）。"""
    try:
        if df is None or df.empty:
            return None
        stock_rows = df[df["证券类别"] == "股票"]
        if stock_rows.empty:
            return None
        col = "总市值" if "总市值" in df.columns else df.columns[2]
        return float(stock_rows.iloc[0][col])
    except Exception:
        return None


@router.delete("/market-overview/cache")
def clear_market_overview_cache():
    with _market_cache_lock:
        _market_cache["data"] = None
        _market_cache["trade_date"] = None
        _market_cache["cache_until"] = None
        _market_cache["version"] = 0
    return {"ok": True, "message": "市场概览缓存已清除"}
