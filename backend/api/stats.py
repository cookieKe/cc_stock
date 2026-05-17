import threading
from datetime import date, timedelta, datetime, time

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
from backend.services.data_sync import get_last_trade_date, get_source_manager

router = APIRouter(prefix="/api/stats", tags=["stats"])

_market_cache = {"data": None, "trade_date": None, "cache_until": None}
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

    data["cached"] = False
    return data


def _fetch_one_index(mgr, symbol: str, name: str, start_str: str, end_str: str) -> dict:
    info = {"name": name, "code": symbol, "latest": None, "change_pct": None,
            "dates": [], "closes": []}
    try:
        df, _ = mgr.fetch_index_kline(symbol, start_str, end_str)
        if not df.empty and len(df) >= 2:
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
    mgr = get_source_manager()
    today_str = str(date.today())
    start_str = str(date.today() - timedelta(days=180))

    sh_index = _fetch_one_index(mgr, "000001", "上证指数", start_str, today_str)
    sz_index = _fetch_one_index(mgr, "399001", "深证成指", start_str, today_str)

    # 活跃市值 OAMV ≈ SMA( Σ(open×amount)/10^7, 10 )
    active_cap = _compute_oamv(db, latest_trade_date)

    # 总市值：从 financials 表取每只股票最新报告期的市值汇总
    total_cap = None
    try:
        from sqlalchemy import func as sql_func
        sub = (
            db.query(
                Financials.stock_code,
                sql_func.max(Financials.report_date).label("max_date"),
            )
            .filter(Financials.market_cap.isnot(None))
            .group_by(Financials.stock_code)
            .subquery()
        )
        cap_sum = (
            db.query(sql_func.sum(Financials.market_cap))
            .join(sub, (Financials.stock_code == sub.c.stock_code)
                  & (Financials.report_date == sub.c.max_date))
            .scalar()
        )
        if cap_sum:
            total_cap = int(cap_sum)
    except Exception:
        pass

    return {
        "indices": [sh_index, sz_index],
        "active_market_cap": active_cap,
        "total_market_cap": total_cap,
        "trade_date": str(latest_trade_date) if latest_trade_date else None,
    }


def _compute_oamv(db: Session, latest_trade_date) -> dict:
    """活跃市值 OAMV: 近似模拟指南针活筹指数。

    daily_raw = Σ(open × amount) / 10^7  (全A股按交易日汇总)
    OAMV = SMA(daily_raw, 10)
    """
    result = {"name": "活跃市值(0AMV)", "latest": None, "change_pct": None,
              "dates": [], "values": []}
    if not latest_trade_date:
        return result

    start = latest_trade_date - timedelta(days=200)
    rows = (
        db.query(
            MarketData.trade_date,
            func.sum(MarketData.open * MarketData.amount).label("daily_sum"),
        )
        .filter(
            MarketData.trade_date >= start,
            MarketData.trade_date <= latest_trade_date,
        )
        .group_by(MarketData.trade_date)
        .order_by(MarketData.trade_date)
        .all()
    )
    if len(rows) < 10:
        return result

    raw = [round(float(r.daily_sum / 10_000_000), 2) if r.daily_sum else None for r in rows]
    dates = [str(r.trade_date) for r in rows]

    # 10日简单移动平均
    oamv = []
    for i in range(len(raw)):
        if i < 9:
            oamv.append(None)
        else:
            window = raw[i - 9:i + 1]
            if all(v is not None for v in window):
                oamv.append(round(sum(window) / 10, 2))
            else:
                oamv.append(None)

    result["dates"] = dates
    result["values"] = oamv
    last_val = None
    for v in reversed(oamv):
        if v is not None:
            last_val = v
            break
    if last_val is not None:
        result["latest"] = last_val
        # 找上一个有效值算涨跌
        found = False
        for v in reversed(oamv):
            if v is not None:
                if found:
                    prev_val = v
                    if prev_val != 0:
                        result["change_pct"] = round((last_val - prev_val) / prev_val * 100, 2)
                    break
                found = True

    return result
