"""Gửi thông báo desktop; trả False khi backend báo lỗi."""

import logging
import sys


logger = logging.getLogger(__name__)


def send_desktop_notification(title: str, message: str) -> bool:
    """True chỉ xác nhận backend nhận yêu cầu, không xác nhận người dùng đã đọc."""
    try:
        from plyer import notification

        if sys.platform == "win32":
            # Win32 dùng bộ đệm UTF-16 gồm cả ký tự kết thúc chuỗi.
            title = title.encode("utf-16-le")[:126].decode("utf-16-le", errors="ignore")
            message = message.encode("utf-16-le")[:510].decode("utf-16-le", errors="ignore")
        notification.notify(title=title, message=message, timeout=10)
        return True
    except Exception as exc:
        logger.warning("Không thể gửi thông báo desktop (%s).", type(exc).__name__)
        return False
