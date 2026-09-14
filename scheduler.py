"""Kiểm tra lịch mỗi phút trong một tiến trình ứng dụng."""

from datetime import datetime
import logging
from threading import Lock

from apscheduler.schedulers.background import BackgroundScheduler

import ai_engine
import database
import notifier


logger = logging.getLogger(__name__)
_scheduler: BackgroundScheduler | None = None
_start_lock = Lock()
_check_lock = Lock()
JOB_ID = "study-reminders"


def check_and_notify() -> None:
    """Cô lập lỗi từng lịch; chỉ đánh dấu completed nếu backend nhận thông báo."""
    try:
        # Cũng tránh trùng nếu được gọi trực tiếp trong lúc job đang chạy.
        if not _check_lock.acquire(blocking=False):
            return
        try:
            tasks = database.get_due_tasks(datetime.now().strftime(database.DATETIME_FORMAT))
            for task in tasks:
                try:
                    message = ai_engine.generate_reminder(task["subject"])
                    if notifier.send_desktop_notification("Đến giờ học!", message):
                        database.mark_task_completed(task["id"])
                        logger.info("Đã gửi lời nhắc cho lịch #%s.", task["id"])
                    else:
                        logger.warning("Lịch #%s vẫn chờ gửi; sẽ thử lại ở lượt sau.", task["id"])
                except Exception as exc:
                    logger.error(
                        "Không thể xử lý lịch #%s (%s); tiếp tục các lịch khác.",
                        task.get("id", "?"), type(exc).__name__,
                    )
        finally:
            _check_lock.release()
    except Exception as exc:
        logger.error("Không thể kiểm tra lịch đến hạn (%s).", type(exc).__name__)


def start_scheduler() -> BackgroundScheduler:
    """Khởi động một scheduler duy nhất, trả instance để CLI shutdown."""
    global _scheduler
    candidate = None
    try:
        with _start_lock:
            if _scheduler is not None and _scheduler.running:
                return _scheduler
            candidate = BackgroundScheduler()
            candidate.add_job(
                check_and_notify,
                trigger="interval",
                minutes=1,
                id=JOB_ID,
                replace_existing=True,
                max_instances=1,
                coalesce=True,
                next_run_time=datetime.now().astimezone(),
            )
            candidate.start()
            _scheduler = candidate
            return _scheduler
    except Exception as exc:
        logger.error("Không thể khởi động scheduler (%s).", type(exc).__name__)
        if candidate is not None and candidate.running:
            try:
                candidate.shutdown(wait=False)
            except Exception as shutdown_error:
                logger.error("Không thể dọn scheduler (%s).", type(shutdown_error).__name__)
        raise
