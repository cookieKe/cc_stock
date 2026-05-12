import json
from typing import List, Dict
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd

from backend.strategy_engine.registry import registry
from backend.models.strategy import Strategy
from backend.models.market_data import MarketData
from backend.models.financials import Financials
from backend.models.stock import Stock


def load_strategies_from_db(db: Session) -> List[dict]:
    """从数据库加载启用的策略配置。"""
    strategies = db.query(Strategy).filter(Strategy.is_enabled == True).order_by(Strategy.id).all()  # noqa: E712
    result = []
    for s in strategies:
        if s.class_path in registry:
            cls = registry.get(s.class_path)
            params = json.loads(s.parameters) if s.parameters else {}
            instance = cls()
            instance.parameters = {**instance.parameters, **params} if params else instance.parameters
            result.append({
                "id": s.id,
                "name": s.name,
                "instance": instance,
                "weight": s.weight,
            })
    return result


def get_kline_data(db: Session, code: str, days: int = 120) -> pd.DataFrame:
    rows = (
        db.query(MarketData)
        .filter(MarketData.stock_code == code)
        .order_by(MarketData.trade_date.asc())
        .limit(days)
        .all()
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "date": r.trade_date,
        "open": r.open, "high": r.high, "low": r.low,
        "close": r.close, "volume": r.volume,
        "amount": r.amount, "turnover": r.turnover,
    } for r in rows])


def get_financials_data(db: Session, code: str) -> pd.DataFrame:
    rows = (
        db.query(Financials)
        .filter(Financials.stock_code == code)
        .order_by(Financials.report_date.desc())
        .limit(4)
        .all()
    )
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame([{
        "report_date": r.report_date,
        "pe": r.pe, "pb": r.pb, "ps": r.ps,
        "roe": r.roe, "roa": r.roa,
        "revenue_growth": r.revenue_growth,
        "profit_growth": r.profit_growth,
        "market_cap": r.market_cap,
    } for r in rows])


def evaluate_stock(db: Session, code: str, strategies: List[dict]) -> Dict[str, float]:
    """对单只股票执行所有策略，返回各策略评分。"""
    results = {}
    kline = None
    fin = None
    for strat in strategies:
        try:
            req = strat["instance"].get_required_data()
            days = req.get("kline_days", 120)
            if kline is None:
                kline = get_kline_data(db, code, days)
            if kline.empty:
                results[strat["name"]] = 0.0
                continue
            s = strat["instance"]
            if hasattr(s, "score") and "financial" in str(type(s)).lower():
                if fin is None:
                    fin = get_financials_data(db, code)
            raw = s.score(code, kline, fin)
            results[strat["name"]] = raw
        except Exception:
            results[strat["name"]] = 0.0
    return results


def aggregate_scores(scores: Dict[str, float], strategies: List[dict]) -> float:
    """加权汇总各策略评分。"""
    total_weight = sum(s["weight"] for s in strategies)
    if total_weight == 0:
        return 0.0
    weighted = sum(
        scores.get(s["name"], 0) * s["weight"]
        for s in strategies
    )
    return round(weighted / total_weight, 2)
