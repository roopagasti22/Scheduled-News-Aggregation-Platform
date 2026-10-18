import logging
from datetime import datetime, timezone
from threading import RLock
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler
from pymongo.errors import PyMongoError

from briefing_service import generate_daily_briefing
from config import NEWS_SCHEDULE_HOUR, NEWS_SCHEDULE_MINUTE, NEWS_TIMEZONE
from news_service import NewsServiceError, collect_and_store_news


logger = logging.getLogger(__name__)

SCHEDULE_INTERVALS = {
    1: "Every minute",
    5: "Every 5 minutes",
    60: "Every hour",
    1440: "Every day",
}

_scheduler: BackgroundScheduler | None = None
_schedule_mode = "daily"
_schedule_interval_minutes = 1440
_last_run_completed_at: datetime | None = None
_last_run_status: str | None = None
_last_articles_stored: int | None = None
_state_lock = RLock()


def run_daily_job() -> None:
    global _last_run_completed_at, _last_run_status, _last_articles_stored

    with _state_lock:
        _last_run_status = "running"
        _last_run_completed_at = None
        _last_articles_stored = None

    try:
        stored_count = collect_and_store_news()
    except NewsServiceError:
        logger.error("Daily job could not collect news; briefing was not generated.")
        with _state_lock:
            _last_run_status = "failed"
            _last_run_completed_at = datetime.now(timezone.utc)
        return
    except PyMongoError:
        logger.error("Daily job could not save news because MongoDB is unavailable.")
        with _state_lock:
            _last_run_status = "failed"
            _last_run_completed_at = datetime.now(timezone.utc)
        return

    logger.info("Daily job stored %s new articles.", stored_count)

    try:
        generate_daily_briefing()
    except PyMongoError:
        logger.error("Daily briefing could not be saved because MongoDB is unavailable.")
        with _state_lock:
            _last_run_status = "failed"
            _last_run_completed_at = datetime.now(timezone.utc)
            _last_articles_stored = stored_count
        return

    with _state_lock:
        _last_run_status = "completed"
        _last_run_completed_at = datetime.now(timezone.utc)
        _last_articles_stored = stored_count


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=ZoneInfo(NEWS_TIMEZONE))
    scheduler.add_job(
        run_daily_job,
        trigger="cron",
        hour=NEWS_SCHEDULE_HOUR,
        minute=NEWS_SCHEDULE_MINUTE,
        id="daily_tech_news_briefing",
        name="Collect news and generate the daily briefing",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=3600,
    )
    return scheduler


def start_scheduler() -> BackgroundScheduler:
    global _scheduler

    scheduler = create_scheduler()
    scheduler.start()
    with _state_lock:
        _scheduler = scheduler
    next_run = scheduler.get_job("daily_tech_news_briefing").next_run_time
    logger.info("Daily news scheduler started. Next run: %s", next_run)
    return scheduler


def get_schedule_status() -> dict[str, object]:
    with _state_lock:
        scheduler = _scheduler
        mode = _schedule_mode
        interval_minutes = _schedule_interval_minutes
        last_run_completed_at = _last_run_completed_at
        last_run_status = _last_run_status
        last_articles_stored = _last_articles_stored

    job = scheduler.get_job("daily_tech_news_briefing") if scheduler else None
    next_run_time = job.next_run_time if job else None
    return {
        "running": bool(scheduler and scheduler.running and job),
        "mode": mode,
        "interval_minutes": interval_minutes,
        "interval_label": SCHEDULE_INTERVALS[interval_minutes],
        "timezone": NEWS_TIMEZONE,
        "next_run_time": next_run_time.isoformat() if next_run_time else None,
        "last_run_completed_at": (
            last_run_completed_at.isoformat() if last_run_completed_at else None
        ),
        "last_run_status": last_run_status,
        "last_articles_stored": last_articles_stored,
    }


def set_schedule_interval(interval_minutes: int) -> dict[str, object]:
    global _schedule_mode, _schedule_interval_minutes

    if isinstance(interval_minutes, bool) or interval_minutes not in SCHEDULE_INTERVALS:
        raise ValueError("Choose an interval of 1, 5, 60, or 1440 minutes.")

    with _state_lock:
        scheduler = _scheduler
        if scheduler is None or not scheduler.running:
            raise RuntimeError("The scheduler is not running.")

        scheduler.reschedule_job(
            "daily_tech_news_briefing",
            trigger="interval",
            minutes=interval_minutes,
        )
        _schedule_mode = "interval"
        _schedule_interval_minutes = interval_minutes

    return get_schedule_status()
