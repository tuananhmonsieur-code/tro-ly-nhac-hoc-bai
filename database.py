"""Lưu lịch nhắc một lần bằng SQLite, dùng giờ địa phương của máy."""

from contextlib import closing
from datetime import datetime, timedelta
import logging
from pathlib import Path
import re
import sqlite3


logger = logging.getLogger(__name__)
DB_PATH = Path(__file__).resolve().parent / "study_tasks.db"
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"


def _validate_timestamp(value: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}", value
    ):
        raise ValueError("Ngày giờ phải có định dạng YYYY-MM-DD HH:MM:SS.")
    datetime.strptime(value, DATETIME_FORMAT)


def init_db() -> None:
    """Tạo bảng; từ chối dữ liệu cũ cần migration, không tự xóa hay sửa lịch."""
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as connection, connection:
            connection.execute(
                "CREATE TABLE IF NOT EXISTS tasks ("
                "id INTEGER PRIMARY KEY, subject TEXT NOT NULL, "
                "study_time TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending')"
            )
            columns = {
                row[1]: (row[2].upper(), row[5])
                for row in connection.execute("PRAGMA table_info(tasks)")
            }
            expected = {
                "id": ("INTEGER", 1), "subject": ("TEXT", 0),
                "study_time": ("TEXT", 0), "status": ("TEXT", 0),
            }
            if columns != expected:
                raise ValueError("Schema lịch cũ cần được chuyển đổi trước khi sử dụng.")
            for subject, study_time, status in connection.execute(
                "SELECT subject, study_time, status FROM tasks"
            ):
                _validate_timestamp(study_time)
                if not isinstance(subject, str) or not subject.strip() or status not in (
                    "pending", "completed"
                ):
                    raise ValueError("Dữ liệu lịch cũ không hợp lệ.")
    except (sqlite3.Error, ValueError) as exc:
        logger.error(
            "Không thể khởi tạo database (%s). Nếu có lịch cũ, cần kiểm tra "
            "schema và chuyển giờ HH:MM sang ngày giờ đầy đủ; dữ liệu được giữ nguyên.",
            type(exc).__name__,
        )
        raise


def add_task(subject: str, study_time: str) -> int:
    """Thêm giờ HH:MM vào hôm nay hoặc ngày mai, trả ID sau khi commit."""
    try:
        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("Tên môn học không được để trống.")
        if not isinstance(study_time, str) or not re.fullmatch(
            r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", study_time
        ):
            raise ValueError("Giờ học phải có dạng HH:MM, từ 00:00 đến 23:59.")
        hour, minute = map(int, study_time.split(":"))
        now = datetime.now()
        due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if due_at < now.replace(second=0, microsecond=0):
            due_at += timedelta(days=1)
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as connection, connection:
            cursor = connection.execute(
                "INSERT INTO tasks (subject, study_time, status) VALUES (?, ?, ?)",
                (" ".join(subject.split()), due_at.strftime(DATETIME_FORMAT), "pending"),
            )
            task_id = cursor.lastrowid
        return task_id
    except (sqlite3.Error, ValueError) as exc:
        logger.error("Không thể thêm lịch học (%s).", type(exc).__name__)
        raise


def get_due_tasks(current_time: str) -> list[dict]:
    """Lấy cả lịch đang đến hạn và quá hạn, bỏ qua lịch đã gửi."""
    try:
        _validate_timestamp(current_time)
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, subject, study_time, status FROM tasks "
                "WHERE status = 'pending' AND study_time <= ? ORDER BY study_time, id",
                (current_time,),
            ).fetchall()
            return [dict(row) for row in rows]
    except (sqlite3.Error, ValueError) as exc:
        logger.error("Không thể đọc lịch đến hạn (%s).", type(exc).__name__)
        raise


def get_all_tasks() -> list[dict]:
    """Trả toàn bộ lịch theo ngày giờ rồi ID."""
    try:
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as connection:
            connection.row_factory = sqlite3.Row
            rows = connection.execute(
                "SELECT id, subject, study_time, status FROM tasks ORDER BY study_time, id"
            ).fetchall()
            return [dict(row) for row in rows]
    except sqlite3.Error as exc:
        logger.error("Không thể đọc danh sách lịch (%s).", type(exc).__name__)
        raise


def mark_task_completed(task_id: int) -> None:
    """Đánh dấu đã yêu cầu hiển thị thông báo, không phải đã học xong."""
    try:
        if type(task_id) is not int or task_id <= 0:
            raise ValueError("ID lịch học phải là số nguyên dương.")
        with closing(sqlite3.connect(DB_PATH, timeout=5)) as connection, connection:
            cursor = connection.execute(
                "UPDATE tasks SET status = 'completed' WHERE id = ?", (task_id,)
            )
            if cursor.rowcount == 0:
                raise ValueError("Không tìm thấy lịch học cần cập nhật.")
    except (sqlite3.Error, ValueError) as exc:
        logger.error("Không thể cập nhật trạng thái lịch (%s).", type(exc).__name__)
        raise
