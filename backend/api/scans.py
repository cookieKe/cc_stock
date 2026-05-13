from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional, List

from backend.database import get_db
from backend.services.market_scanner import scan_market, get_latest_ranking, get_scan_history
from backend.scan_logger import logger

_log = logger.getChild("api")
router = APIRouter(prefix="/api/scans", tags=["scans"])


@router.post("/run")
def run_scan(strategy_name: str = "", db: Session = Depends(get_db)):
    _log.info(f"POST /api/scans/run strategy_name='{strategy_name}'")
    from backend.models.strategy import Strategy
    strategy_ids = None
    if strategy_name:
        s = db.query(Strategy).filter(Strategy.name == strategy_name).first()
        if s:
            strategy_ids = [s.id]
            _log.info(f"  策略名 '{strategy_name}' -> strategy_ids={strategy_ids}")
        else:
            _log.warning(f"  策略名 '{strategy_name}' 未在DB中找到!")
    else:
        _log.info(f"  strategy_name为空, 将扫描全部启用策略")
    result = scan_market(db, strategy_ids)
    _log.info(f"POST /api/scans/run 完成: total_scanned={result.get('total_scanned')} total_ranked={result.get('total_ranked')}")
    return result


@router.get("/latest")
def latest_ranking(strategy_name: str = "", limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    result = get_latest_ranking(db, strategy_name if strategy_name else None, limit, offset)
    _log.info(f"GET /api/scans/latest strategy_name='{strategy_name}' limit={limit} offset={offset} -> total={result.get('total')} items={len(result.get('items',[]))}")
    return result


@router.get("/history/{code}")
def stock_scan_history(code: str, days: int = 30, db: Session = Depends(get_db)):
    return get_scan_history(db, code, days)
