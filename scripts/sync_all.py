"""Standalone script to sync K-line data for all stocks.
Usage:
  python scripts/sync_all.py                    # full sync
  python scripts/sync_all.py --limit 500        # first 500 stocks
  python scripts/sync_all.py --days 180         # custom days back
  python scripts/sync_all.py --code 000001      # single stock
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database import SessionLocal
from backend.models.stock import Stock
from backend.services.data_sync import sync_daily_kline

if __name__ == "__main__":
    days = 180
    limit = 0
    code = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--days" and i + 1 < len(sys.argv):
            days = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--limit" and i + 1 < len(sys.argv):
            limit = int(sys.argv[i + 1])
            i += 2
        elif sys.argv[i] == "--code" and i + 1 < len(sys.argv):
            code = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    db = SessionLocal()
    try:
        codes = None
        if code:
            codes = [code]
        elif limit > 0:
            codes = [s[0] for s in db.query(Stock.code)
                     .filter(Stock.is_active == True).order_by(Stock.code).limit(limit).all()]

        result = sync_daily_kline(db=db, codes=codes, days_back=days, max_workers=0)
        print(f"\nDone in {result['elapsed_seconds']}s")
        print(f"  Total stocks: {result['total_stocks']}")
        print(f"  Skipped: {result['skipped']}")
        print(f"  Synced stocks: {result['synced_stocks']}")
        print(f"  Synced records: {result['synced_records']}")
        print(f"  Failed: {result['failed']}")
        if result["failed_codes"]:
            print(f"  Failed codes: {result['failed_codes'][:20]}")
    finally:
        db.close()
