import time
from datetime import date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func, insert
import pandas as pd

from backend.database import SessionLocal
from backend.models.stock import Stock
from backend.models.market_data import MarketData
from backend.models.financials import Financials
from backend.data_sources.akshare_source import AkshareSource
from backend.data_sources.baostock_source import BaostockSource
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


_source_manager = None
_source_names = None


def get_source_manager() -> DataSourceManager:
    global _source_manager
    if _source_manager is None:
        _source_manager = DataSourceManager()
        if settings.tushare_enabled and settings.tushare_token:
            _source_manager.register(TushareSource())
        if settings.akshare_enabled:
            _source_manager.register(AkshareSource())
        _source_manager.register(BaostockSource())
    return _source_manager


def get_source_names() -> list[str]:
    global _source_names
    if _source_names is None:
        _source_names = []
        if settings.tushare_enabled and settings.tushare_token:
            _source_names.append("tushare")
        if settings.akshare_enabled:
            _source_names.append("akshare")
        _source_names.append("baostock")
    return _source_names


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


def _fetch_one_stock(code: str, start_date: str, end_date: str, source_name: str = None):
    """Fetch K-line for one stock in a fresh session. If source_name given, use only that source."""
    db = SessionLocal()
    try:
        df, _ = _fetch_from_source(code, start_date, end_date, source_name)
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


def _fetch_from_source(code: str, start_date: str, end_date: str, source_name: str = None):
    """Fetch K-line data with retry. If source_name given, try it first then fallback to others."""
    mgr = get_source_manager()
    max_retries = settings.api_retry_count
    backoff = settings.api_retry_backoff
    last_error = None

    # Order sources: preferred source first, then others
    sources = mgr.sources
    if source_name:
        preferred = [s for s in sources if s.name == source_name]
        rest = [s for s in sources if s.name != source_name]
        sources = preferred + rest

    for source in sources:
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
        # If this source returned empty (not exception), try next source

    raise RuntimeError(f"所有数据源均失败。最后错误: {last_error}")


def _sync_via_tushare_batch(db: Session, to_fetch: list[tuple], end_date: str) -> dict | None:
    """使用 Tushare 批量API同步日K线。一次请求获取全市场一天的数据。

    返回同步统计 dict，若 Tushare 不可用则返回 None。
    """
    mgr = get_source_manager()
    ts_source = next((s for s in mgr.sources if s.name == "tushare"), None)
    if ts_source is None or not ts_source.is_available():
        return None

    codes_to_fetch = {c for c, _ in to_fetch}
    start_map = {c: s for c, s in to_fetch}
    min_start = min(s for _, s in to_fetch)

    # 1. Fetch all data via Tushare batch API
    try:
        df = ts_source.fetch_daily_kline_batch(min_start, end_date)
    except Exception:
        return None  # fall back to per-stock path

    if df.empty:
        failed_codes = [c for c, _ in to_fetch]
        return {"synced_records": 0, "synced_stocks": 0, "failed": len(failed_codes), "failed_codes": failed_codes[:50]}

    # 2. Filter to target codes and per-stock start dates
    df = df[df["code"].isin(codes_to_fetch)]
    df = df[df.apply(lambda row: str(row["date"]).replace("-", "") >= start_map.get(row["code"], min_start), axis=1)]

    if df.empty:
        failed_codes = [c for c, _ in to_fetch]
        return {"synced_records": 0, "synced_stocks": 0, "failed": len(failed_codes), "failed_codes": failed_codes[:50]}

    # 3. Batch query existing (stock_code, trade_date) pairs
    rows = (
        db.query(MarketData.stock_code, MarketData.trade_date)
        .filter(MarketData.stock_code.in_(list(codes_to_fetch)))
        .all()
    )
    existing_pairs = {(r[0], r[1]) for r in rows}

    # 4. Collect new records
    new_records = []
    synced_stocks = set()

    for _, row in df.iterrows():
        code = row["code"]
        trade_date = row["date"]
        if isinstance(trade_date, str):
            trade_date = pd.to_datetime(trade_date).date()

        if (code, trade_date) in existing_pairs:
            continue

        new_records.append({
            "stock_code": code,
            "trade_date": trade_date,
            "open": float(_safe_val(row["open"]) or 0),
            "high": float(_safe_val(row["high"]) or 0),
            "low": float(_safe_val(row["low"]) or 0),
            "close": float(_safe_val(row["close"]) or 0),
            "volume": float(_safe_val(row["volume"]) or 0),
            "amount": float(_safe_val(row.get("amount", 0)) or 0),
            "turnover": float(_safe_val(row.get("turnover", 0)) or 0),
            "source": "tushare",
        })
        synced_stocks.add(code)

    # 5. Bulk insert
    if new_records:
        stmt = insert(MarketData)
        if "sqlite" in settings.database_url:
            stmt = stmt.prefix_with("OR IGNORE")
        else:
            stmt = stmt.on_conflict_do_nothing(constraint="uq_stock_date")
        db.execute(stmt.values(new_records))
        db.commit()

    failed_codes = [c for c, _ in to_fetch if c not in synced_stocks]
    return {
        "synced_records": len(new_records),
        "synced_stocks": len(synced_stocks),
        "failed": len(failed_codes),
        "failed_codes": failed_codes[:50],
    }


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

    # Phase 1: determine which stocks actually need fetching (single DB query)
    # Skip only if: (1) data is current AND (2) has enough history
    min_records = int(days_back * 0.6)
    check_db = SessionLocal()
    try:
        rows = (
            check_db.query(
                MarketData.stock_code,
                func.max(MarketData.trade_date),
                func.count(MarketData.id),
            )
            .filter(MarketData.stock_code.in_(codes))
            .group_by(MarketData.stock_code)
            .all()
        )
        stock_status = {r[0]: (r[1], r[2]) for r in rows}
    finally:
        check_db.close()

    skipped = 0
    to_fetch = []
    for c in codes:
        last, count = stock_status.get(c, (None, 0))
        if last and last >= today - timedelta(days=1) and count >= min_records:
            skipped += 1
        else:
            if last and last > today - timedelta(days=days_back) and last < today - timedelta(days=1):
                # Partial data within range but not current — continue from last date
                actual_start = (last + timedelta(days=1)).strftime("%Y%m%d")
            else:
                # No data, old data, or current but incomplete history — fetch from start
                actual_start = default_start
            to_fetch.append((c, actual_start))

    if not to_fetch:
        return {"synced_records": 0, "synced_stocks": 0, "skipped": skipped, "failed": 0, "failed_codes": [], "total_stocks": len(codes), "elapsed_seconds": round(time.time() - start_time, 1)}

    # Phase 2: fetch data
    # Try Tushare batch path first — one request per trade date covers all stocks
    batch_result = None
    work_db = db if db else SessionLocal()
    own_db = db is None
    try:
        batch_result = _sync_via_tushare_batch(work_db, to_fetch, end_date)
    except Exception:
        batch_result = None

    if batch_result is not None:
        # Retry any failed codes via per-stock fallback
        if batch_result.get("failed", 0) > 0:
            failed_set = set(batch_result["failed_codes"])
            retry_tasks = [(c, s) for c, s in to_fetch if c in failed_set]
            source_names = get_source_names()
            for i, (c, actual_start) in enumerate(retry_tasks):
                src = source_names[i % len(source_names)] if source_names else None
                status, stock_code, count = _fetch_one_stock(c, actual_start, end_date, src)
                if status == "ok":
                    batch_result["synced_stocks"] += 1
                    batch_result["synced_records"] += count
                    batch_result["failed"] -= 1
                    batch_result["failed_codes"].remove(stock_code)
        if own_db:
            work_db.close()
        elapsed = round(time.time() - start_time, 1)
        return {
            **batch_result,
            "skipped": skipped,
            "total_stocks": len(codes),
            "elapsed_seconds": elapsed,
        }

    # Fallback: Tushare unavailable — sequential per-stock path
    if own_db:
        work_db.close()
    source_names = get_source_names()
    synced = 0
    failed = 0
    failed_codes = []

    tasks = []
    for i, (c, actual_start) in enumerate(to_fetch):
        src = source_names[i % len(source_names)] if source_names else None
        tasks.append((c, actual_start, end_date, src))

    for c, actual_start, end, src in tasks:
        status, stock_code, count = _fetch_one_stock(c, actual_start, end, src)
        if status == "ok":
            synced += count
        elif status == "fail":
            failed += 1
            failed_codes.append(stock_code)

    processed = len(to_fetch) - failed
    elapsed = round(time.time() - start_time, 1)
    return {
        "synced_records": synced,
        "synced_stocks": processed,
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
