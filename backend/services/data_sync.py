import concurrent.futures
import time
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func
import pandas as pd

from backend.database import SessionLocal
from backend.models.stock import Stock
from backend.models.market_data import MarketData
from backend.models.financials import Financials
from backend.data_sources.akshare_source import AkshareSource
from backend.data_sources.tushare_source import TushareSource
from backend.data_sources.base import DataSourceManager
from backend.config import settings


def _safe_val(val):
    """Convert numpy NaN to None for SQLite compatibility."""
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def get_source_manager() -> DataSourceManager:
    mgr = DataSourceManager()
    if settings.akshare_enabled:
        mgr.register(AkshareSource())
    if settings.tushare_enabled:
        mgr.register(TushareSource())
    return mgr


def sync_stock_list(db: Session) -> int:
    """同步全A股股票列表，返回新增数量。"""
    mgr = get_source_manager()
    df, source_name = mgr.fetch_stock_list()
    added = 0
    for _, row in df.iterrows():
        code = str(row["code"]).zfill(6)
        existing = db.query(Stock).filter(Stock.code == code).first()
        if not existing:
            db.add(Stock(
                code=code,
                name=str(row.get("name", "")),
                exchange=str(row.get("exchange", "SH")),
                industry=str(row.get("industry", "")),
                listed_date=_safe_val(row.get("listed_date")),
            ))
            added += 1
    db.commit()
    return added


def _stock_data_status(code: str):
    """Return (max_date, record_count) for a stock. Uses a fresh session."""
    db = SessionLocal()
    try:
        row = db.query(
            func.max(MarketData.trade_date),
            func.count(MarketData.id),
        ).filter(MarketData.stock_code == code).first()
        return (row[0], row[1]) if row else (None, 0)
    finally:
        db.close()


def _fetch_one_stock(code: str, start_date: str, end_date: str):
    """Fetch K-line for one stock in a fresh session. Returns (status, code, count_or_error)."""
    db = SessionLocal()
    try:
        df, _ = _fetch_from_source(code, start_date, end_date)
        if df is None or df.empty:
            return ("empty", code, 0)

        count = 0
        for _, row in df.iterrows():
            trade_date = row["date"]
            if isinstance(trade_date, str):
                trade_date = pd.to_datetime(trade_date).date()
            existing = db.query(MarketData).filter(
                MarketData.stock_code == code,
                MarketData.trade_date == trade_date,
            ).first()
            if not existing:
                db.add(MarketData(
                    stock_code=code,
                    trade_date=trade_date,
                    open=float(_safe_val(row["open"]) or 0),
                    high=float(_safe_val(row["high"]) or 0),
                    low=float(_safe_val(row["low"]) or 0),
                    close=float(_safe_val(row["close"]) or 0),
                    volume=float(_safe_val(row["volume"]) or 0),
                    amount=float(_safe_val(row.get("amount", 0)) or 0),
                    turnover=float(_safe_val(row.get("turnover", 0)) or 0),
                ))
                count += 1
        db.commit()
        return ("ok", code, count)
    except Exception as e:
        db.rollback()
        return ("fail", code, str(e))
    finally:
        db.close()


def _fetch_from_source(code: str, start_date: str, end_date: str):
    """Fetch K-line data with retry. Uses a fresh manager each call for thread safety."""
    mgr = get_source_manager()
    max_retries = settings.api_retry_count
    backoff = settings.api_retry_backoff
    last_error = None

    for source in mgr.sources:
        if not source.is_available():
            continue
        fn = getattr(source, "fetch_daily_kline")
        for attempt in range(max_retries):
            try:
                result = fn(code, start_date, end_date)
                if result is not None and (not isinstance(result, pd.DataFrame) or not result.empty):
                    return result, source.name
            except Exception as e:
                last_error = e
                if attempt < max_retries - 1:
                    time.sleep(backoff ** attempt)

    raise RuntimeError(f"所有数据源均失败。最后错误: {last_error}")


def sync_daily_kline(
    db: Session = None,
    code: str = None,
    codes: list[str] = None,
    days_back: int = 180,
    max_workers: int = 10,
) -> dict:
    """增量同步日K线数据。

    优化策略：
    1. 已是最新数据的股票跳过API调用
    2. 部分有数据的只从断点续传
    3. 多线程并发拉取
    4. 每日仅拉取最近 days_back 天 (默认6个月)

    返回 {synced, skipped, failed, failed_codes, elapsed_seconds}
    """
    start_time = time.time()
    today = date.today()
    end_date = today.strftime("%Y%m%d")
    default_start = (today - timedelta(days=days_back)).strftime("%Y%m%d")

    if codes:
        pass  # caller provided explicit list
    elif code:
        codes = [code]
    else:
        check_db = SessionLocal()
        try:
            codes = [s[0] for s in check_db.query(Stock.code).filter(Stock.is_active == True).order_by(Stock.code).all()]
        finally:
            check_db.close()

    # Phase 1: determine which stocks actually need fetching
    # Skip only if: (1) data is current AND (2) has enough history
    min_records = int(days_back * 0.6)  # ~108 for 180 days (accounts for holidays)
    skipped = 0
    to_fetch = []
    for c in codes:
        last, count = _stock_data_status(c)
        if last and last >= today - timedelta(days=1) and count >= min_records:
            skipped += 1
        else:
            # Compute the actual start date for this stock
            if last and last > today - timedelta(days=days_back):
                actual_start = (last + timedelta(days=1)).strftime("%Y%m%d")
            else:
                actual_start = default_start
            to_fetch.append((c, actual_start))

    if not to_fetch:
        return {"synced_records": 0, "synced_stocks": 0, "skipped": skipped, "failed": 0, "failed_codes": [], "total_stocks": len(codes), "elapsed_seconds": round(time.time() - start_time, 1)}

    # Phase 2: fetch data
    synced = 0
    failed = 0
    failed_codes = []

    if max_workers <= 1:
        # Sequential mode — avoids py_mini_racer V8 crash in multi-thread
        for c, actual_start in to_fetch:
            status, stock_code, count = _fetch_one_stock(c, actual_start, end_date)
            if status == "ok":
                synced += count
            elif status == "fail":
                failed += 1
                failed_codes.append(stock_code)
    else:
        # Parallel mode — faster but may crash on Windows with akshare
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(_fetch_one_stock, c, actual_start, end_date): c
                for c, actual_start in to_fetch
            }
            for future in concurrent.futures.as_completed(futures):
                status, stock_code, count = future.result()
                if status == "ok":
                    synced += count
                elif status == "fail":
                    failed += 1
                    failed_codes.append(stock_code)

    elapsed = round(time.time() - start_time, 1)
    return {
        "synced_records": synced,
        "synced_stocks": len(to_fetch) - failed,
        "skipped": skipped,
        "failed": failed,
        "failed_codes": failed_codes[:50],
        "total_stocks": len(codes),
        "elapsed_seconds": elapsed,
    }


def sync_financials(db: Session, code: str = None) -> int:
    """同步财务数据。"""
    mgr = get_source_manager()
    synced = 0
    codes = [code] if code else [s.code for s in db.query(Stock.code).filter(Stock.is_active == True).all()]
    for i, c in enumerate(codes):
        try:
            df, _ = mgr.fetch_financials(c)
            if df.empty:
                continue
            for _, row in df.iterrows():
                report_date = row["report_date"]
                if isinstance(report_date, str):
                    report_date = pd.to_datetime(report_date).date()
                existing = db.query(Financials).filter(
                    Financials.stock_code == c,
                    Financials.report_date == report_date,
                ).first()
                if not existing:
                    db.add(Financials(
                        stock_code=c,
                        report_date=report_date,
                        pe=float(_safe_val(row.get("pe", 0)) or 0),
                        pb=float(_safe_val(row.get("pb", 0)) or 0),
                        ps=float(_safe_val(row.get("ps", 0)) or 0),
                        roe=float(_safe_val(row.get("roe", 0)) or 0),
                        roa=float(_safe_val(row.get("roa", 0)) or 0),
                        revenue_growth=float(_safe_val(row.get("revenue_growth", 0)) or 0),
                        profit_growth=float(_safe_val(row.get("profit_growth", 0)) or 0),
                        market_cap=float(_safe_val(row.get("market_cap", 0)) or 0),
                    ))
                    synced += 1
            if i > 0 and i % 50 == 0:
                db.commit()
        except Exception:
            pass
    db.commit()
    return synced


def get_last_trade_date(db: Session) -> date:
    """获取数据库中最近一个交易日"""
    result = db.query(func.max(MarketData.trade_date)).scalar()
    return result or date.today() - timedelta(days=7)
