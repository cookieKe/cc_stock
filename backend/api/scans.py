from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from backend.database import get_db
from backend.services.market_scanner import scan_market, get_latest_ranking, get_scan_history

router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("/run")
def run_scan(strategy_ids: Optional[List[int]] = None, db: Session = Depends(get_db)):
    result = scan_market(db, strategy_ids)
    return result


@router.get("/latest")
def latest_ranking(strategy_name: str = "", limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    return get_latest_ranking(db, strategy_name if strategy_name else None, limit, offset)


@router.get("/history/{code}")
def stock_scan_history(code: str, days: int = 30, db: Session = Depends(get_db)):
    return get_scan_history(db, code, days)
