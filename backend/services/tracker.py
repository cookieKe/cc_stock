from datetime import date
from sqlalchemy.orm import Session
from typing import List, Optional
import numpy as np

from backend.models.watchlist import Watchlist
from backend.models.market_data import MarketData
from backend.models.stock import Stock


def _get_latest_close(db: Session, code: str) -> float:
    """获取本地DB最新收盘价，不可用时返回0。"""
    row = (
        db.query(MarketData)
        .filter(MarketData.stock_code == code, MarketData.close > 0)
        .order_by(MarketData.trade_date.desc())
        .first()
    )
    return float(row.close) if row and row.close else 0


def add_to_watchlist(db: Session, code: str, notes: str = "", source: str = "手动") -> Watchlist:
    """添加股票到追踪列表。加入价取自本地最新收盘价，不调外部API。"""
    existing = db.query(Watchlist).filter(
        Watchlist.stock_code == code, Watchlist.is_active == True  # noqa: E712
    ).first()
    if existing:
        return existing

    stock = db.query(Stock).filter(Stock.code == code).first()
    if not stock:
        return Watchlist()

    added_price = _get_latest_close(db, code)
    if added_price <= 0:
        return Watchlist()  # 无有效价格，拒绝添加

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
        source=source,
    )
    db.add(wl)
    db.commit()
    return wl


def remove_from_watchlist(db: Session, watchlist_id: int):
    """移除追踪。活跃项软删除，已结束项硬删除。"""
    wl = db.query(Watchlist).filter(Watchlist.id == watchlist_id).first()
    if wl:
        if wl.is_active:
            wl.is_active = False
        else:
            db.delete(wl)
        db.commit()


def update_watchlist_prices(db: Session) -> int:
    """更新所有追踪股的最新收盘价和累计收益。纯本地计算，不调外部API。"""
    items = db.query(Watchlist).filter(Watchlist.is_active == True).all()  # noqa: E712
    if not items:
        return 0

    updated = 0
    for wl in items:
        price = _get_latest_close(db, wl.stock_code)
        if price > 0:
            wl.latest_price = price
        # price <= 0 时保持原 latest_price 不变

        if wl.added_price and wl.added_price > 0:
            if wl.latest_price and wl.latest_price > 0:
                wl.cumulative_return = round((wl.latest_price / wl.added_price - 1) * 100, 2)
            wl.holding_days = (date.today() - wl.added_date).days
            if wl.highest_price is None or wl.latest_price > wl.highest_price:
                wl.highest_price = wl.latest_price
            if wl.lowest_price is None or wl.latest_price < wl.lowest_price:
                wl.lowest_price = wl.latest_price

        updated += 1

    db.commit()
    return updated


def _item_to_dict(wl: Watchlist) -> dict:
    """将 Watchlist 对象序列化为字典，包含所有显示字段。"""
    sell_return = None
    if wl.sell_price and wl.added_price and wl.added_price > 0:
        sell_return = round((wl.sell_price / wl.added_price - 1) * 100, 2)
    return {
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
        "source": wl.source or "手动",
        "target_price": wl.target_price,
        "stop_loss_price": wl.stop_loss_price,
        "sell_price": wl.sell_price,
        "sell_return": sell_return,
    }


def get_watchlist_stats(db: Session) -> dict:
    """获取追踪组合统计，拆分活跃/已结束。顶层统计保持向后兼容。"""
    active_items = db.query(Watchlist).filter(Watchlist.is_active == True).all()  # noqa: E712
    closed_items = db.query(Watchlist).filter(Watchlist.is_active == False).all()  # noqa: E712

    if not active_items and not closed_items:
        return {"count": 0, "message": "暂无追踪股票"}

    # --- 活跃持仓统计（顶层字段向后兼容 Dashboard） ---
    returns = [wl.cumulative_return for wl in active_items if wl.cumulative_return is not None]
    positive = sum(1 for r in returns if r > 0)
    negative = sum(1 for r in returns if r < 0)

    result = {
        "count": len(active_items),
        "avg_return": round(np.mean(returns), 2) if returns else 0,
        "median_return": round(np.median(returns), 2) if returns else 0,
        "max_return": round(max(returns), 2) if returns else 0,
        "min_return": round(min(returns), 2) if returns else 0,
        "positive_ratio": round(positive / len(returns) * 100, 2) if returns else 0,
        "positive_count": positive,
        "negative_count": negative,
        "today_avg_change": _get_today_avg_change(db, active_items),
        "best": _get_best_worst(active_items, best=True),
        "worst": _get_best_worst(active_items, best=False),
        "active_items": [_item_to_dict(wl) for wl in active_items],
        "closed_items": [_item_to_dict(wl) for wl in closed_items],
    }

    # --- 已结束持仓统计 ---
    closed_returns = [
        r for r in (_item_to_dict(wl)["sell_return"] for wl in closed_items)
        if r is not None
    ]
    result["closed_stats"] = {
        "count": len(closed_items),
        "avg_sell_return": round(np.mean(closed_returns), 2) if closed_returns else 0,
    }

    return result


def update_watchlist_item(db: Session, item_id: int, data: dict) -> dict:
    """部分更新追踪项的价格字段。当卖出价从无到有时自动标记为非活跃。"""
    wl = db.query(Watchlist).filter(Watchlist.id == item_id).first()
    if not wl:
        return {}

    # 更新提供的字段
    if "target_price" in data:
        wl.target_price = data["target_price"]
    if "stop_loss_price" in data:
        wl.stop_loss_price = data["stop_loss_price"]
    if "sell_price" in data:
        old_sell = wl.sell_price
        wl.sell_price = data["sell_price"]
        # 卖出价从无到有 → 标记非活跃；从有到无 → 恢复活跃
        if old_sell is None and wl.sell_price is not None:
            wl.is_active = False
        elif old_sell is not None and wl.sell_price is None:
            wl.is_active = True

    db.commit()
    db.refresh(wl)
    return _item_to_dict(wl)


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
    """追踪组合与沪深300同期表现对比。优先从本地DB取指数数据。"""
    items = db.query(Watchlist).filter(Watchlist.is_active == True).all()  # noqa: E712
    if not items:
        return None

    earliest = min(wl.added_date for wl in items)
    if not earliest:
        return None

    # 从本地DB取沪深300日K线
    rows = (
        db.query(MarketData)
        .filter(
            MarketData.stock_code == "000300",
            MarketData.trade_date >= earliest,
            MarketData.trade_date <= date.today(),
        )
        .order_by(MarketData.trade_date.asc())
        .all()
    )

    if len(rows) < 2:
        return None

    bench_return = (rows[-1].close / rows[0].close - 1) * 100
    returns = [wl.cumulative_return for wl in items if wl.cumulative_return is not None]
    avg_return = float(np.mean(returns)) if returns else 0
    return {
        "portfolio_avg_return": round(avg_return, 2),
        "benchmark_return": round(bench_return, 2),
        "excess_return": round(avg_return - bench_return, 2),
    }
