from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db
from backend.models.stock import Stock
from backend.services.data_sync import sync_stock_list, sync_daily_kline, sync_financials, get_last_trade_date

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/")
def list_stocks(
    keyword: str = "",
    exchange: str = "",
    industry: str = "",
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    q = db.query(Stock).filter(Stock.is_active == True)  # noqa: E712
    if keyword:
        q = q.filter(
            (Stock.code.like(f"%{keyword}%")) | (Stock.name.like(f"%{keyword}%"))
        )
    if exchange:
        q = q.filter(Stock.exchange == exchange)
    if industry:
        q = q.filter(Stock.industry == industry)
    total = q.count()
    rows = q.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [{"code": r.code, "name": r.name, "exchange": r.exchange, "industry": r.industry, "listed_date": str(r.listed_date) if r.listed_date else None} for r in rows],
    }


@router.get("/{code}")
def get_stock_detail(code: str, db: Session = Depends(get_db)):
    stock = db.query(Stock).filter(Stock.code == code).first()
    if not stock:
        return {"error": "股票不存在"}
    return {"code": stock.code, "name": stock.name, "exchange": stock.exchange, "industry": stock.industry}


@router.post("/sync/list")
def api_sync_stock_list(db: Session = Depends(get_db)):
    added = sync_stock_list(db)
    return {"status": "ok", "added": added}


@router.post("/sync/kline")
def api_sync_kline(code: Optional[str] = None, days_back: int = 180, max_workers: int = 0, db: Session = Depends(get_db)):
    result = sync_daily_kline(db, code=code, days_back=days_back, max_workers=max_workers)
    return {"status": "ok", **result}


@router.post("/sync/financials")
def api_sync_financials(code: Optional[str] = None, db: Session = Depends(get_db)):
    synced = sync_financials(db, code)
    return {"status": "ok", "synced": synced}


@router.post("/init")
def api_init(max_stocks: int = 300, db: Session = Depends(get_db)):
    """一键初始化：同步股票列表 + 并行同步最近6个月K线。"""
    count = db.query(Stock).count()
    if count == 0:
        added = sync_stock_list(db)
    else:
        added = count

    codes = [s[0] for s in db.query(Stock.code).filter(Stock.is_active == True).order_by(Stock.code).limit(max_stocks).all()]  # noqa: E712
    if not codes:
        return {"status": "ok", "message": "股票列表为空，请先同步股票列表", "stocks": added}

    result = sync_daily_kline(codes=codes, days_back=180, max_workers=10)

    return {
        "status": "ok",
        "message": f"股票列表 {added} 只，K线已同步 {result['synced_stocks']} 只 ({result['synced_records']} 条)，跳过 {result['skipped']} 只，失败 {result['failed']} 只",
        "stocks": added,
        **result,
    }


@router.post("/sync/recent")
def api_sync_recent(days: int = 2, db: Session = Depends(get_db)):
    """同步最近 N 天 K 线数据，用于手动刷新数据。已是最新的股票自动跳过。"""
    result = sync_daily_kline(db, days_back=days)
    last_date = get_last_trade_date(db)
    return {"status": "ok", **result, "last_trade_date": str(last_date)}
