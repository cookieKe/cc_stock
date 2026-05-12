from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Optional
import numpy as np

from backend.models.watchlist import Watchlist
from backend.models.market_data import MarketData
from backend.models.stock import Stock
from backend.data_sources.akshare_source import AkshareSource


def add_to_watchlist(db: Session, code: str, notes: str = "") -> Watchlist:
    """添加股票到追踪列表，记录加入时价格。"""
    existing = db.query(Watchlist).filter(
        Watchlist.stock_code == code, Watchlist.is_active == True  # noqa: E712
    ).first()
    if existing:
        return existing

    stock = db.query(Stock).filter(Stock.code == code).first()
    if not stock:
        return Watchlist()

    source = AkshareSource()
    quote = source.fetch_realtime_quote(code)
    added_price = quote.get("price", 0) if quote else 0
    if added_price == 0:
        latest = (
            db.query(MarketData)
            .filter(MarketData.stock_code == code)
            .order_by(MarketData.trade_date.desc())
            .first()
        )
        if latest:
            added_price = latest.close

    wl = Watchlist(
        stock_code=code,
        stock_name=stock.name,
        added_date=date.today(),
        added_price=added_price,
        latest_price=added_price,
        cumulative_return=0,
        holding_days=0,
        highest_price=added_price,
        lowest_price=added_price,
        notes=notes,
    )
    db.add(wl)
    db.commit()
    return wl


def remove_from_watchlist(db: Session, watchlist_id: int):
    """移除追踪（软删除，标记is_active=False）。"""
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if wl:
        wl.is_active = False
        db.commit()


def update_watchlist_prices(db: Session) -> int:
    """更新所有追踪股的最新价格和收益率。"""
    items = db.query(Watchlist).filter(Watchlist.is_active == True).all()  # noqa: E712
    source = AkshareSource()
    updated = 0
    for wl in items:
        try:
            quote = source.fetch_realtime_quote(wl.stock_code)
            if not quote or quote.get("price", 0) == 0:
                latest = (
                    db.query(MarketData)
                    .filter(MarketData.stock_code == wl.stock_code)
                    .order_by(MarketData.trade_date.desc())
                    .first()
                )
                if latest:
                    wl.latest_price = latest.close
            else:
                wl.latest_price = quote["price"]

            if wl.latest_price and wl.added_price:
                wl.cumulative_return = round((wl.latest_price / wl.added_price - 1) * 100, 2)
                wl.holding_days = (date.today() - wl.added_date).days
                if wl.highest_price is None or wl.latest_price > wl.highest_price:
                    wl.highest_price = wl.latest_price
                if wl.lowest_price is None or wl.latest_price < wl.lowest_price:
                    wl.lowest_price = wl.latest_price
            updated += 1
        except Exception:
            pass
    db.commit()
    return updated


def get_watchlist_stats(db: Session) -> dict:
    """获取追踪组合统计。"""
    items = db.query(Watchlist).filter(Watchlist.is_active == True).all()  # noqa: E712
    if not items:
        return {"count": 0, "message": "暂无追踪股票"}

    returns = [wl.cumulative_return for wl in items if wl.cumulative_return is not None]
    positive = sum(1 for r in returns if r > 0)
    negative = sum(1 for r in returns if r < 0)

    return {
        "count": len(items),
        "avg_return": round(np.mean(returns), 2) if returns else 0,
        "median_return": round(np.median(returns), 2) if returns else 0,
        "max_return": round(max(returns), 2) if returns else 0,
        "min_return": round(min(returns), 2) if returns else 0,
        "positive_ratio": round(positive / len(returns) * 100, 2) if returns else 0,
        "positive_count": positive,
        "negative_count": negative,
        "today_avg_change": _get_today_avg_change(db, items),
        "best": _get_best_worst(items, best=True),
        "worst": _get_best_worst(items, best=False),
        "items": [
            {
                "id": wl.id,
                "code": wl.stock_code,
                "name": wl.stock_name,
                "added_date": str(wl.added_date),
                "added_price": wl.added_price,
                "latest_price": wl.latest_price,
                "cumulative_return": wl.cumulative_return,
                "holding_days": wl.holding_days,
                "highest_price": wl.highest_price,
                "lowest_price": wl.lowest_price,
            }
            for wl in items
        ],
    }


def _get_today_avg_change(db: Session, items: List[Watchlist]) -> float:
    today = date.today()
    total_change = 0
    count = 0
    for wl in items:
        row = (
            db.query(MarketData)
            .filter(MarketData.stock_code == wl.stock_code, MarketData.trade_date == today)
            .first()
        )
        if row and wl.latest_price and row.close:
            change = (row.close / wl.latest_price - 1) * 100
            total_change += change
            count += 1
    return round(total_change / count, 2) if count > 0 else 0


def _get_best_worst(items: List[Watchlist], best: bool = True) -> dict:
    target = max if best else min
    wl = target(
        [w for w in items if w.cumulative_return is not None],
        key=lambda w: w.cumulative_return,
        default=None
    )
    if not wl:
        return {}
    return {"code": wl.stock_code, "name": wl.stock_name, "return": wl.cumulative_return}


def get_watchlist_compare_benchmark(db: Session) -> Optional[dict]:
    """追踪组合与沪深300同期表现对比。"""
    items = db.query(Watchlist).filter(Watchlist.is_active == True).all()  # noqa: E712
    if not items:
        return None
    from backend.data_sources.akshare_source import AkshareSource
    source = AkshareSource()
    try:
        earliest = min(wl.added_date for wl in items)
        df, _ = source.fetch_index_kline("000300", earliest.strftime("%Y%m%d"), date.today().strftime("%Y%m%d"))
        if df.empty:
            return None
        bench_return = (df.iloc[-1]["close"] / df.iloc[0]["close"] - 1) * 100
        avg_return = np.mean([wl.cumulative_return for wl in items if wl.cumulative_return is not None])
        return {
            "portfolio_avg_return": round(avg_return, 2),
            "benchmark_return": round(bench_return, 2),
            "excess_return": round(avg_return - bench_return, 2),
        }
    except Exception:
        return None
