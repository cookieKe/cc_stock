from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
import pandas as pd
import numpy as np

from backend.database import get_db
from backend.models.market_data import MarketData

router = APIRouter(prefix="/api/charts", tags=["charts"])


@router.get("/kline/{code}")
def get_kline(
    code: str,
    start_date: str = "",
    end_date: str = "",
    days: int = 250,
    db: Session = Depends(get_db),
):
    rows = (
        db.query(MarketData)
        .filter(MarketData.stock_code == code)
        .order_by(MarketData.trade_date.asc())
        .all()
    )
    if start_date:
        start = pd.to_datetime(start_date).date()
        rows = [r for r in rows if r.trade_date >= start]
    if end_date:
        end = pd.to_datetime(end_date).date()
        rows = [r for r in rows if r.trade_date <= end]
    rows = rows[-days:]

    dates = [str(r.trade_date) for r in rows]
    ohlc = [[r.open, r.close, r.low, r.high] for r in rows]
    volumes = [r.volume for r in rows]

    mas = {}
    closes = [r.close for r in rows]
    for period in [5, 10, 20, 60]:
        if len(closes) >= period:
            ma = pd.Series(closes).rolling(period).mean().tolist()
            mas[f"ma{period}"] = [round(v, 2) if not pd.isna(v) else None for v in ma]
        else:
            mas[f"ma{period}"] = [None] * len(closes)

    return {
        "code": code,
        "dates": dates,
        "ohlc": ohlc,
        "volumes": volumes,
        **mas,
    }


@router.get("/kdj/{code}")
def get_kdj(code: str, n: int = 9, days: int = 120, db: Session = Depends(get_db)):
    rows = (
        db.query(MarketData)
        .filter(MarketData.stock_code == code)
        .order_by(MarketData.trade_date.asc())
        .all()
    )[-days:]
    if len(rows) < n:
        return {"error": "数据不足"}

    closes = [r.close for r in rows]
    highs = [r.high for r in rows]
    lows = [r.low for r in rows]

    k, d, j = _calc_kdj(highs, lows, closes, n)
    return {
        "code": code,
        "dates": [str(r.trade_date) for r in rows],
        "k": k,
        "d": d,
        "j": j,
    }


def _calc_kdj(highs, lows, closes, n=9):
    k, d, j = [], [], []
    for i in range(len(closes)):
        if i < n - 1:
            k.append(None)
            d.append(None)
            j.append(None)
            continue
        hh = max(highs[i - n + 1:i + 1])
        ll = min(lows[i - n + 1:i + 1])
        rsv = (closes[i] - ll) / (hh - ll + 1e-9) * 100
        prev_k = k[-1] if k and k[-1] is not None else 50
        prev_d = d[-1] if d and d[-1] is not None else 50
        k_val = 2 / 3 * prev_k + 1 / 3 * rsv
        d_val = 2 / 3 * prev_d + 1 / 3 * k_val
        j_val = 3 * k_val - 2 * d_val
        k.append(round(k_val, 2))
        d.append(round(d_val, 2))
        j.append(round(j_val, 2))
    return k, d, j


@router.get("/volume/{code}")
def get_volume_chart(code: str, days: int = 120, db: Session = Depends(get_db)):
    rows = (
        db.query(MarketData)
        .filter(MarketData.stock_code == code)
        .order_by(MarketData.trade_date.asc())
        .all()
    )[-days:]

    dates = [str(r.trade_date) for r in rows]
    volumes = [r.volume for r in rows]
    up_flags = [r.close >= r.open for r in rows]
    ma5 = pd.Series(volumes).rolling(5).mean().tolist()
    ma20 = pd.Series(volumes).rolling(20).mean().tolist()

    return {
        "code": code,
        "dates": dates,
        "volumes": volumes,
        "up_flags": up_flags,
        "ma5": [round(v, 2) if not pd.isna(v) else None for v in ma5],
        "ma20": [round(v, 2) if not pd.isna(v) else None for v in ma20],
    }
