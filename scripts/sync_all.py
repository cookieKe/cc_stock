"""Standalone script to sync K-line data for all stocks.
Run directly: python scripts/sync_all.py [--days 180] [--limit 0]
Use --limit N to sync only the first N stocks.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.services.data_sync import sync_daily_kline, get_last_trade_date
from backend.database import SessionLocal

if __name__ == "__main__":
    days = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--days" else 180
    limit = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--limit" else (
        int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[3] == "--limit" else 0
    )

    print(f"Starting sync: days_back={days}, sequential mode")
    if limit > 0:
        print(f"Limited to first {limit} stocks")

    db = SessionLocal()
    try:
        from backend.models.stock import Stock
        codes = [s[0] for s in db.query(Stock.code).filter(Stock.is_active == True).order_by(Stock.code).all()]
        if limit > 0:
            codes = codes[:limit]

        result = sync_daily_kline(codes=codes, days_back=days, max_workers=0)
        print(f"\nDone!")
        print(f"  Synced records: {result['synced_records']}")
        print(f"  Synced stocks:  {result['synced_stocks']}")
        print(f"  Skipped:        {result['skipped']}")
        print(f"  Failed:         {result['failed']}")
        print(f"  Total stocks:   {result['total_stocks']}")
        print(f"  Elapsed:        {result['elapsed_seconds']}s")
        if result['failed_codes']:
            print(f"  Failed codes:   {result['failed_codes'][:20]}...")
    finally:
        db.close()
