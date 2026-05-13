from datetime import date
from sqlalchemy.orm import Session
from typing import List, Dict

from backend.models.stock import Stock
from backend.models.scan_result import ScanResult
from backend.strategy_engine.evaluator import (
    load_strategies_from_db, evaluate_stock, aggregate_scores
)
from backend.config import settings
from backend.scan_logger import logger

_log = logger.getChild("scanner")


def scan_market(db: Session, strategy_ids: List[int] = None) -> dict:
    """扫描全市场，执行启用策略，返回排名结果。"""
    _log.info(f"===== 扫描开始 strategy_ids={strategy_ids} =====")

    all_strategies = load_strategies_from_db(db)
    if strategy_ids:
        _log.info(f"过滤前策略数: {len(all_strategies)}, 过滤条件: {strategy_ids}")
        all_strategies = [s for s in all_strategies if s["id"] in strategy_ids]
    _log.info(f"最终使用策略: {[(s['id'], s['name'], s['weight']) for s in all_strategies]}")

    if not all_strategies:
        _log.warning("没有启用的策略，扫描中止")
        return {"error": "没有启用的策略"}

    _log.info(f"删除今日({date.today()})已有扫描结果...")
    deleted = db.query(ScanResult).filter(ScanResult.scan_date == date.today()).delete()
    _log.info(f"删除了 {deleted} 条旧记录")

    codes = [s[0] for s in db.query(Stock.code).filter(Stock.is_active == True).order_by(Stock.code).all()]  # noqa: E712
    batch_size = settings.scan_batch_size
    scan_date = date.today()
    _log.info(f"活跃股票总数: {len(codes)}, 批大小: {batch_size}")

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
        if all_results:
            _log.debug(f"批次 {i//batch_size + 1}: 累计 {len(all_results)} 只有得分股票")
        db.commit()

    all_results.sort(key=lambda x: x["weighted_score"], reverse=True)
    _log.info(f"排序完成，有得分的股票总数: {len(all_results)}")

    # Log top and bottom
    if all_results:
        top_n = min(10, len(all_results))
        _log.info(f"Top {top_n}:")
        for i in range(top_n):
            r = all_results[i]
            _log.info(f"  #{i+1} {r['code']} {r['name']} weighted={r['weighted_score']} scores={r['scores']}")
        if len(all_results) > 10:
            _log.info(f"  ... (省略 {len(all_results) - 20} 条) ...")
            for i in range(max(10, len(all_results) - 10), len(all_results)):
                r = all_results[i]
                _log.info(f"  #{i+1} {r['code']} {r['name']} weighted={r['weighted_score']} scores={r['scores']}")

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
    _log.info(f"写入 {len(all_results)} 条扫描结果到DB，完成")

    # Also log how get_latest_ranking would respond
    from sqlalchemy import func
    latest = db.query(func.max(ScanResult.scan_date)).scalar()
    for s in all_strategies:
        cnt = db.query(ScanResult).filter(
            ScanResult.scan_date == latest, ScanResult.strategy_name == s["name"]
        ).count()
        _log.info(f"  策略 {s['name']}: DB中 {cnt} 条记录")

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
