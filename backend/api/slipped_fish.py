import threading
from datetime import date, timedelta, datetime, time
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from backend.database import get_db
from backend.models.market_data import MarketData
from backend.models.scan_result import ScanResult
from backend.models.stock import Stock
from backend.api.charts import _calc_kdj

router = APIRouter(prefix="/api/slipped-fish", tags=["slipped-fish"])

LOOKBACK_CALENDAR_DAYS = 7
KDJ_WARMPAD_DAYS = 15
J_THRESHOLD = 13
PRICE_CHANGE_MIN = 5.0
SCORE_MAX = 80.0

_cache = {"data": None, "trade_date": None, "cache_until": None}
_cache_lock = threading.Lock()


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


def _compute_cache_until(db: Session, trade_date: date) -> datetime:
    next_td = _find_next_trade_date(db, trade_date)
    return datetime.combine(next_td, time(9, 0))


def _in_cache_window(now: datetime, trade_date: date, cache_until: datetime) -> bool:
    start = datetime.combine(trade_date, time(16, 0))
    return start <= now <= cache_until


def _compute_items(db: Session) -> dict:
    """Run the full slipped-fish query. Factored out so cache hit can skip it."""
    latest_trade_date = db.query(func.max(MarketData.trade_date)).scalar()
    if not latest_trade_date:
        return {"count": 0, "items": [], "scan_date": None, "trade_date": None}

    lookback_start = latest_trade_date - timedelta(days=LOOKBACK_CALENDAR_DAYS)
    data_start = latest_trade_date - timedelta(days=LOOKBACK_CALENDAR_DAYS + KDJ_WARMPAD_DAYS)

    active_codes = db.query(Stock.code).filter(Stock.is_active == True).subquery()

    rows = (
        db.query(
            MarketData.stock_code,
            MarketData.trade_date,
            MarketData.high,
            MarketData.low,
            MarketData.close,
        )
        .filter(
            MarketData.stock_code.in_(active_codes),
            MarketData.trade_date >= data_start,
            MarketData.trade_date <= latest_trade_date,
        )
        .order_by(MarketData.stock_code, MarketData.trade_date)
        .all()
    )

    latest_scan_date = db.query(func.max(ScanResult.scan_date)).scalar()
    score_map = {}
    if latest_scan_date:
        score_rows = (
            db.query(
                ScanResult.stock_code,
                ScanResult.stock_name,
                func.max(ScanResult.weighted_score).label("best_score"),
            )
            .filter(ScanResult.scan_date == latest_scan_date)
            .group_by(ScanResult.stock_code, ScanResult.stock_name)
            .all()
        )
        for r in score_rows:
            score_map[r.stock_code] = {"name": r.stock_name, "score": r.best_score}

    stock_data = defaultdict(list)
    for r in rows:
        stock_data[r.stock_code].append(r)

    results = []
    for code, data_rows in stock_data.items():
        if len(data_rows) < 12:
            continue

        window_rows = [r for r in data_rows if r.trade_date >= lookback_start]
        if len(window_rows) < 2:
            continue

        closes = [r.close for r in data_rows]
        highs = [r.high for r in data_rows]
        lows = [r.low for r in data_rows]

        k, d, j = _calc_kdj(highs, lows, closes, n=9)

        window_indices = [i for i, r in enumerate(data_rows) if r.trade_date >= lookback_start]
        window_j = [j[i] for i in window_indices if j[i] is not None]
        if not window_j:
            continue

        min_j = min(window_j)
        if min_j >= J_THRESHOLD:
            continue

        first_close = data_rows[window_indices[0]].close
        last_close = data_rows[window_indices[-1]].close
        price_change_pct = round((last_close - first_close) / first_close * 100, 2)

        if price_change_pct <= PRICE_CHANGE_MIN:
            continue

        stock_info = score_map.get(code)
        if stock_info is None:
            continue

        score = stock_info["score"]
        if score >= SCORE_MAX:
            continue

        results.append({
            "code": code,
            "name": stock_info["name"],
            "min_j": round(min_j, 2),
            "price_change_pct": price_change_pct,
            "first_close": first_close,
            "last_close": last_close,
            "score": score,
        })

    results.sort(key=lambda x: (x["score"], -x["price_change_pct"]))

    return {
        "count": len(results),
        "scan_date": str(latest_scan_date) if latest_scan_date else None,
        "trade_date": str(latest_trade_date),
        "items": results,
    }


@router.get("/")
def get_slipped_fish(db: Session = Depends(get_db)):
    now = datetime.now()

    latest_trade_date = db.query(func.max(MarketData.trade_date)).scalar()

    with _cache_lock:
        cached = _cache["data"]
        cached_td = _cache["trade_date"]
        cached_until = _cache["cache_until"]
    if cached is not None and cached_td == latest_trade_date and cached_until is not None:
        if _in_cache_window(now, cached_td, cached_until):
            resp = dict(cached)
            resp["cached"] = True
            resp["cache_until"] = cached_until.isoformat()
            return resp

    data = _compute_items(db)

    if latest_trade_date:
        cache_until = _compute_cache_until(db, latest_trade_date)
        with _cache_lock:
            _cache["data"] = data
            _cache["trade_date"] = latest_trade_date
            _cache["cache_until"] = cache_until
        data["cache_until"] = cache_until.isoformat()
    data["cached"] = False
    return data


@router.delete("/cache")
def clear_slipped_fish_cache():
    with _cache_lock:
        _cache["data"] = None
        _cache["trade_date"] = None
        _cache["cache_until"] = None
    return {"ok": True, "message": "缓存已清除"}
