from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date
import json

from backend.database import SessionLocal
from backend.config import settings
from backend.services.data_sync import sync_daily_kline
from backend.services.market_scanner import scan_market
from backend.services.tracker import update_watchlist_prices, get_watchlist_stats
from backend.notification.im_bot import NotificationService

scheduler = BackgroundScheduler()


def _daily_job():
    """每日定时任务：同步K线 → 扫描排名 → 更新追踪 → 推送通知"""
    db = SessionLocal()
    try:
        sync_daily_kline(db, days_back=2, max_workers=10)
        update_watchlist_prices(db)

        scan_result = scan_market(db)
        tracker_stats = get_watchlist_stats(db)

        notif_service = NotificationService(db)
        if settings.im_webhook_url:
            notif_service.add_im_bot(
                webhook_url=settings.im_webhook_url,
                bot_type=settings.im_bot_type,
            )
        if "error" not in scan_result:
            notif_service.send_scan_report(scan_result)
        notif_service.send_tracker_report(tracker_stats)
    except Exception as e:
        db.rollback()
    finally:
        db.close()


def start_scheduler():
    hour = settings.scan_schedule_hour
    minute = settings.scan_schedule_minute
    scheduler.add_job(
        _daily_job,
        trigger=CronTrigger(hour=hour, minute=minute),
        id="daily_scan",
        name="每日市场扫描",
        replace_existing=True,
    )
    scheduler.start()


def stop_scheduler():
    if scheduler.running:
        scheduler.shutdown(wait=False)
