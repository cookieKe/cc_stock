from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models.stock import Stock
from backend.services.tracker import (
    add_to_watchlist, remove_from_watchlist, update_watchlist_prices,
    get_watchlist_stats, get_watchlist_compare_benchmark, update_watchlist_item,
)

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("/")
def list_watchlist(db: Session = Depends(get_db)):
    return get_watchlist_stats(db)


@router.post("/")
def add_stock(data: dict, db: Session = Depends(get_db)):
    code = data.get("code", "")
    if not code:
        return {"error": "股票代码不能为空"}
    notes = data.get("notes", "")
    source = data.get("source", "手动")
    wl = add_to_watchlist(db, code, notes, source)
    if not wl.stock_code:
        exists = db.query(Stock).filter(Stock.code == code).first()
        if not exists:
            return {"error": "股票不存在"}
        return {"error": "该股票无有效价格数据，请先同步日K线"}
    return {
        "id": wl.id,
        "code": wl.stock_code,
        "name": wl.stock_name,
        "added_date": str(wl.added_date),
        "added_price": wl.added_price,
    }


@router.delete("/{watchlist_id}")
def remove_stock(watchlist_id: int, db: Session = Depends(get_db)):
    remove_from_watchlist(db, watchlist_id)
    return {"status": "ok"}


@router.post("/update-prices")
def trigger_price_update(db: Session = Depends(get_db)):
    updated = update_watchlist_prices(db)
    return {"status": "ok", "updated": updated}


@router.get("/benchmark")
def compare_benchmark(db: Session = Depends(get_db)):
    result = get_watchlist_compare_benchmark(db)
    if not result:
        return {"error": "无法获取基准数据"}
    return result


@router.put("/{item_id}")
def update_item(item_id: int, data: dict, db: Session = Depends(get_db)):
    """更新追踪项的价格字段（预期价/止损价/卖出价）。"""
    result = update_watchlist_item(db, item_id, data)
    if not result:
        return {"error": "追踪项不存在"}
    return result
