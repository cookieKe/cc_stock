import json
import numpy as np
import pandas as pd
from datetime import date
from sqlalchemy.orm import Session
from typing import List, Dict

from backend.strategy_engine.registry import registry
from backend.strategy_engine.evaluator import get_kline_data, get_financials_data
from backend.models.backtest import Backtest
from backend.config import settings


def run_backtest(
    db: Session,
    strategy_name: str,
    codes: List[str],
    start_date: str,
    end_date: str,
    top_n: int = 10,
    rebalance_freq: int = 20,
) -> dict:
    """滚动回测：每隔rebalance_freq个交易日调仓，买入评分Top N，等权持有。"""
    cls = registry.get(strategy_name)
    strategy = cls()

    kline_cache: Dict[str, pd.DataFrame] = {}
    for code in codes:
        df = get_kline_data(db, code, days=500)
        if not df.empty:
            df = df[(df["date"] >= pd.to_datetime(start_date).date()) & (df["date"] <= pd.to_datetime(end_date).date())]
            if not df.empty:
                kline_cache[code] = df.reset_index(drop=True)

    if not kline_cache:
        return {"error": "回测区间内无可用数据"}

    all_dates = sorted(set().union(*[set(df["date"]) for df in kline_cache.values()]))

    nav = 1.0
    nav_curve = []
    trades_log = []
    holdings: Dict[str, float] = {}
    cash = 1.0
    position_date = None

    for i, trade_date in enumerate(all_dates):
        if position_date is None or (i - all_dates.index(position_date)) >= rebalance_freq or i == 0:
            scores = {}
            for code in kline_cache:
                df_t = kline_cache[code][kline_cache[code]["date"] <= trade_date]
                if len(df_t) < 60:
                    continue
                fin = get_financials_data(db, code)
                try:
                    scores[code] = strategy.score(code, df_t, fin)
                except Exception:
                    scores[code] = 0
            ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_n]
            if ranked:
                holdings = {code: 1.0 / len(ranked) for code, _ in ranked}
                cash = 0
                trades_log.append({
                    "date": str(trade_date),
                    "action": "rebalance",
                    "holdings": [{"code": c, "weight": w} for c, w in holdings.items()],
                })
            position_date = trade_date

        daily_return = 0
        for code, weight in holdings.items():
            df_t = kline_cache[code][kline_cache[code]["date"] <= trade_date]
            if len(df_t) < 2:
                continue
            prev_close = df_t.iloc[-2]["close"] if len(df_t) >= 2 else df_t.iloc[-1]["close"]
            cur_close = df_t.iloc[-1]["close"]
            daily_return += weight * (cur_close / prev_close - 1)

        nav *= (1 + daily_return)
        nav_curve.append({"date": str(trade_date), "nav": round(nav, 6), "daily_return": round(daily_return, 6)})

    metrics = _calculate_metrics(nav_curve, start_date, end_date)
    return {"nav_curve": nav_curve, "trades": trades_log, **metrics}


def run_backtest_with_benchmark(
    db: Session,
    strategy_name: str,
    codes: List[str],
    start_date: str,
    end_date: str,
    top_n: int = 10,
) -> dict:
    """跑策略回测 + 基准（沪深300）对比。"""
    result = run_backtest(db, strategy_name, codes, start_date, end_date, top_n)
    if "error" in result:
        return result

    from backend.services.data_sync import get_source_manager
    mgr = get_source_manager()
    try:
        bench_df, _ = mgr.fetch_index_kline(settings.benchmark_symbol, start_date, end_date)
        if not bench_df.empty:
            bench_start = bench_df.iloc[0]["close"]
            bench_nav = []
            for _, row in bench_df.iterrows():
                bench_nav.append({"date": str(row["date"]), "nav": round(row["close"] / bench_start, 6)})
            result["benchmark_nav"] = bench_nav
            bench_return = bench_df.iloc[-1]["close"] / bench_df.iloc[0]["close"] - 1
            result["benchmark_return"] = round(bench_return * 100, 2)
            result["alpha"] = round(result["total_return"] - result["benchmark_return"], 2)
    except Exception:
        pass
    return result


def _calculate_metrics(nav_curve: list, start_date: str, end_date: str) -> dict:
    if not nav_curve or len(nav_curve) < 2:
        return {"total_return": 0, "annual_return": 0, "sharpe_ratio": 0, "max_drawdown": 0, "win_rate": 0, "profit_loss_ratio": 0}

    navs = [p["nav"] for p in nav_curve]
    returns = np.array([p["daily_return"] for p in nav_curve[1:]])
    total_return = (navs[-1] - 1.0) * 100

    trading_days = len(nav_curve)
    annual_return = ((navs[-1]) ** (252 / max(trading_days, 1)) - 1) * 100

    risk_free_daily = settings.risk_free_rate / 252
    excess = returns - risk_free_daily
    sharpe = (excess.mean() / (excess.std() + 1e-9)) * np.sqrt(252)

    peak = navs[0]
    max_dd = 0
    for n in navs:
        peak = max(peak, n)
        dd = (peak - n) / peak * 100
        max_dd = max(max_dd, dd)

    win_rate = (returns > 0).sum() / len(returns) * 100 if len(returns) > 0 else 0
    gains = returns[returns > 0]
    losses = abs(returns[returns < 0])
    pl_ratio = gains.mean() / (losses.mean() + 1e-9) if len(gains) > 0 and len(losses) > 0 else 0

    info_ratio = 0
    if len(returns) > 0:
        info_ratio = returns.mean() / (returns.std() + 1e-9) * np.sqrt(252)

    return {
        "total_return": round(total_return, 2),
        "annual_return": round(annual_return, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown": round(max_dd, 2),
        "win_rate": round(win_rate, 2),
        "profit_loss_ratio": round(pl_ratio, 2),
        "alpha": 0,
        "information_ratio": round(info_ratio, 2),
        "trading_days": trading_days,
    }


def save_backtest(db: Session, strategy_id: int, strategy_name: str, start_date: str, end_date: str, result: dict):
    bt = Backtest(
        strategy_id=strategy_id,
        strategy_name=strategy_name,
        start_date=pd.to_datetime(start_date).date(),
        end_date=pd.to_datetime(end_date).date(),
        total_return=result.get("total_return", 0),
        annual_return=result.get("annual_return", 0),
        sharpe_ratio=result.get("sharpe_ratio", 0),
        max_drawdown=result.get("max_drawdown", 0),
        win_rate=result.get("win_rate", 0),
        profit_loss_ratio=result.get("profit_loss_ratio", 0),
        benchmark_return=result.get("benchmark_return", 0),
        alpha=result.get("alpha", 0),
        information_ratio=result.get("information_ratio", 0),
        daily_nav=json.dumps(result.get("nav_curve", [])),
        trades=json.dumps(result.get("trades", [])),
    )
    db.add(bt)
    db.commit()
