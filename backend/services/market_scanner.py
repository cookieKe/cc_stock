from datetime import date
from sqlalchemy.orm import Session
from typing import List, Dict

from backend.models.stock import Stock
from backend.models.scan_result import ScanResult
from backend.strategy_engine.evaluator import (
    load_strategies_from_db, evaluate_stock, aggregate_scores
)
from backend.config import settings


def scan_market(db: Session, strategy_ids: List[int] = None) -> dict:
    """扫描全市场，执行启用策略，返回排名结果。"""
    all_strategies = load_strategies_from_db(db)
    if strategy_ids:
        all_strategies = [s for s in all_strategies if s["id"] in strategy_ids]
    if not all_strategies:
        return {"error": "没有启用的策略"}

    db.query(ScanResult).filter(ScanResult.scan_date == date.today()).delete()

    codes = [s[0] for s in db.query(Stock.code).filter(Stock.is_active == True).order_by(Stock.code).all()]  # noqa: E712
    batch_size = settings.scan_batch_size
    scan_date = date.today()

    all_results = []
    for i in range(0, len(codes), batch_size):
        batch = codes[i:i + batch_size]
        for code in batch:
            try:
                stock = db.query(Stock).filter(Stock.code == code).first()
                if not stock:
                    continue
                scores = evaluate_stock(db, code, all_strategies)
                if not scores or all(v == 0 for v in scores.values()):
                    continue
                weighted = aggregate_scores(scores, all_strategies)
                all_results.append({
                    "code": code,
                    "name": stock.name,
                    "scores": scores,
                    "weighted_score": weighted,
                })
            except Exception:
                pass
        db.commit()

    all_results.sort(key=lambda x: x["weighted_score"], reverse=True)
    for rank, r in enumerate(all_results, 1):
        r["rank"] = rank
        for strat_name, raw_score in r["scores"].items():
            strategy = next((s for s in all_strategies if s["name"] == strat_name), None)
            db.add(ScanResult(
                scan_date=scan_date,
                stock_code=r["code"],
                stock_name=r["name"],
                strategy_id=strategy["id"] if strategy else 0,
                strategy_name=strat_name,
                raw_score=raw_score,
                weighted_score=round(raw_score * (strategy["weight"] if strategy else 1), 2),
                rank=rank,
            ))
    db.commit()

    return {
        "scan_date": str(scan_date),
        "total_scanned": len(codes),
        "total_ranked": len(all_results),
        "strategies_used": [s["name"] for s in all_strategies],
        "top_20": [
            {"rank": r["rank"], "code": r["code"], "name": r["name"], "score": r["weighted_score"]}
            for r in all_results[:20]
        ],
    }


def get_latest_ranking(db: Session, strategy_name: str = None, limit: int = 50, offset: int = 0) -> dict:
    """获取最近一次扫描排名。多策略时按股票去重取最高综合分。返回分页结构。"""
    from sqlalchemy import func
    latest_date = db.query(func.max(ScanResult.scan_date)).scalar()
    if not latest_date:
        return {"items": [], "total": 0, "limit": limit, "offset": offset, "scan_date": None}

    if strategy_name:
        total = (
            db.query(func.count(ScanResult.id))
            .filter(ScanResult.scan_date == latest_date, ScanResult.strategy_name == strategy_name)
            .scalar()
        )
        rows = (
            db.query(ScanResult)
            .filter(ScanResult.scan_date == latest_date, ScanResult.strategy_name == strategy_name)
            .order_by(ScanResult.rank.asc())
            .offset(offset).limit(limit)
            .all()
        )
        items = [
            {"rank": offset + i + 1, "code": r.stock_code, "name": r.stock_name, "score": r.weighted_score}
            for i, r in enumerate(rows)
        ]
        return {"items": items, "total": total, "limit": limit, "offset": offset, "scan_date": str(latest_date)}

    rows = (
        db.query(ScanResult)
        .filter(ScanResult.scan_date == latest_date)
        .order_by(ScanResult.weighted_score.desc())
        .all()
    )
    seen = set()
    deduped = []
    for r in rows:
        if r.stock_code not in seen:
            seen.add(r.stock_code)
            deduped.append(r)

    total = len(deduped)
    page = deduped[offset:offset + limit]
    items = [
        {"rank": offset + i + 1, "code": r.stock_code, "name": r.stock_name, "score": r.weighted_score}
        for i, r in enumerate(page)
    ]
    return {"items": items, "total": total, "limit": limit, "offset": offset, "scan_date": str(latest_date)}


def get_scan_history(db: Session, code: str, days: int = 30) -> List[dict]:
    """获取某只股票的历史排名变化。"""
    from datetime import timedelta
    cutoff = date.today() - timedelta(days=days)
    rows = (
        db.query(ScanResult)
        .filter(ScanResult.stock_code == code, ScanResult.scan_date >= cutoff)
        .order_by(ScanResult.scan_date.desc())
        .all()
    )
    return [
        {"date": str(r.scan_date), "strategy": r.strategy_name, "score": r.weighted_score, "rank": r.rank}
        for r in rows
    ]
