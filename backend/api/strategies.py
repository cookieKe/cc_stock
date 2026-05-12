import json
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from backend.database import get_db
from backend.models.strategy import Strategy
from backend.strategy_engine.registry import registry
from backend.services.backtest_runner import run_backtest_with_benchmark, save_backtest
from backend.models.backtest import Backtest

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("/")
def list_strategies(db: Session = Depends(get_db)):
    builtin = registry.list_strategies()
    db_strategies = db.query(Strategy).all()
    result = []
    for s in db_strategies:
        result.append({
            "id": s.id,
            "name": s.name,
            "display_name": s.display_name,
            "description": s.description,
            "class_path": s.class_path,
            "parameters": json.loads(s.parameters) if s.parameters else {},
            "weight": s.weight,
            "is_enabled": s.is_enabled,
            "is_builtin": True,
        })
    for name, info in builtin.items():
        if not any(r["name"] == name for r in result):
            result.append({
                "id": 0,
                "name": name,
                "display_name": info["display_name"],
                "description": info["description"],
                "class_path": name,
                "parameters": info["parameters"],
                "weight": 1.0,
                "is_enabled": False,
                "is_builtin": True,
            })
    return result


@router.post("/")
def create_strategy(data: dict, db: Session = Depends(get_db)):
    existing = db.query(Strategy).filter(Strategy.name == data["name"]).first()
    if existing:
        return {"error": f"策略 '{data['name']}' 已存在"}
    s = Strategy(
        name=data["name"],
        display_name=data.get("display_name", data["name"]),
        description=data.get("description", ""),
        class_path=data.get("class_path", data["name"]),
        parameters=json.dumps(data.get("parameters", {})),
        weight=data.get("weight", 1.0),
        is_enabled=data.get("is_enabled", True),
    )
    db.add(s)
    db.commit()
    return {"status": "ok", "id": s.id}


@router.put("/{strategy_id}")
def update_strategy(strategy_id: int, data: dict, db: Session = Depends(get_db)):
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not s:
        return {"error": "策略不存在"}
    if "display_name" in data:
        s.display_name = data["display_name"]
    if "description" in data:
        s.description = data["description"]
    if "parameters" in data:
        s.parameters = json.dumps(data["parameters"])
    if "weight" in data:
        s.weight = data["weight"]
    if "is_enabled" in data:
        s.is_enabled = data["is_enabled"]
    db.commit()
    return {"status": "ok"}


@router.delete("/{strategy_id}")
def delete_strategy(strategy_id: int, db: Session = Depends(get_db)):
    s = db.query(Strategy).filter(Strategy.id == strategy_id).first()
    if not s:
        return {"error": "策略不存在"}
    db.delete(s)
    db.commit()
    return {"status": "ok"}


@router.post("/{strategy_name}/backtest")
def run_strategy_backtest(
    strategy_name: str,
    data: dict,
    db: Session = Depends(get_db),
):
    if strategy_name not in registry:
        return {"error": f"策略 '{strategy_name}' 未注册"}
    start_date = data.get("start_date", "2024-01-01")
    end_date = data.get("end_date", "2025-12-31")
    codes = data.get("codes", [])
    if not codes:
        from backend.models.stock import Stock
        codes = [s[0] for s in db.query(Stock.code).filter(Stock.is_active == True).limit(300).all()]  # noqa: E712
    top_n = data.get("top_n", 10)
    result = run_backtest_with_benchmark(db, strategy_name, codes, start_date, end_date, top_n)
    if "error" not in result:
        strategy = db.query(Strategy).filter(Strategy.name == strategy_name).first()
        save_backtest(db, strategy.id if strategy else 0, strategy_name, start_date, end_date, result)
    return result


@router.get("/{strategy_name}/backtest/history")
def list_backtest_history(strategy_name: str, db: Session = Depends(get_db)):
    rows = (
        db.query(Backtest)
        .filter(Backtest.strategy_name == strategy_name)
        .order_by(Backtest.created_at.desc())
        .limit(20)
        .all()
    )
    return [
        {
            "id": r.id,
            "start_date": str(r.start_date),
            "end_date": str(r.end_date),
            "total_return": r.total_return,
            "annual_return": r.annual_return,
            "sharpe_ratio": r.sharpe_ratio,
            "max_drawdown": r.max_drawdown,
            "win_rate": r.win_rate,
            "profit_loss_ratio": r.profit_loss_ratio,
            "alpha": r.alpha,
            "information_ratio": r.information_ratio,
            "created_at": str(r.created_at),
        }
        for r in rows
    ]


@router.get("/{strategy_name}/backtest/{backtest_id}")
def get_backtest_detail(strategy_name: str, backtest_id: int, db: Session = Depends(get_db)):
    r = db.query(Backtest).filter(Backtest.id == backtest_id).first()
    if not r:
        return {"error": "回测记录不存在"}
    return {
        "id": r.id,
        "strategy_name": r.strategy_name,
        "start_date": str(r.start_date),
        "end_date": str(r.end_date),
        "total_return": r.total_return,
        "annual_return": r.annual_return,
        "sharpe_ratio": r.sharpe_ratio,
        "max_drawdown": r.max_drawdown,
        "win_rate": r.win_rate,
        "profit_loss_ratio": r.profit_loss_ratio,
        "benchmark_return": r.benchmark_return,
        "alpha": r.alpha,
        "information_ratio": r.information_ratio,
        "nav_curve": json.loads(r.daily_nav) if r.daily_nav else [],
        "trades": json.loads(r.trades) if r.trades else [],
    }
