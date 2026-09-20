"""Nạp cấu hình Azure OpenAI; thiếu cấu hình vẫn cho phép dùng lời nhắc dự phòng."""

import logging
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv


logger = logging.getLogger(__name__)

try:
    load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env", override=False)
except (OSError, UnicodeError) as exc:
    logger.warning("Không thể đọc file .env (%s).", type(exc).__name__)

AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip()
AZURE_OPENAI_DEPLOYMENT_NAME = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "").strip()
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash"


def validate_config() -> bool:
    """Kiểm tra cấu hình đã nạp và chỉ log tên biến thiếu hoặc sai.

    Trả False để tầng AI dùng lời nhắc dự phòng, không dừng ứng dụng.
    Hàm chỉ kiểm tra cấu hình cục bộ, không xác thực key qua mạng.
    """
    required_values = {
        "AZURE_OPENAI_API_KEY": AZURE_OPENAI_API_KEY,
        "AZURE_OPENAI_ENDPOINT": AZURE_OPENAI_ENDPOINT,
        "AZURE_OPENAI_DEPLOYMENT_NAME": AZURE_OPENAI_DEPLOYMENT_NAME,
        "AZURE_OPENAI_API_VERSION": AZURE_OPENAI_API_VERSION,
    }
    valid = True
    for name, value in required_values.items():
        if not value:
            logger.warning("Thiếu biến môi trường hoặc giá trị rỗng: %s.", name)
            valid = False

    if AZURE_OPENAI_ENDPOINT:
        try:
            endpoint = urlsplit(AZURE_OPENAI_ENDPOINT)
            endpoint_valid = (
                endpoint.scheme == "https"
                and bool(endpoint.hostname)
                and endpoint.username is None
                and endpoint.password is None
                and not endpoint.query
                and not endpoint.fragment
                and not any(char.isspace() for char in AZURE_OPENAI_ENDPOINT)
                and "\\" not in AZURE_OPENAI_ENDPOINT
                and (endpoint.port is None or endpoint.port > 0)
            )
        except ValueError:
            endpoint_valid = False

        if not endpoint_valid:
            logger.warning(
                "AZURE_OPENAI_ENDPOINT phải là URL HTTPS hợp lệ, "
                "không chứa thông tin đăng nhập, query hoặc fragment."
            )
            valid = False

    return valid


def validate_gemini_config() -> bool:
    """Kiểm tra cấu hình Gemini cục bộ mà không gửi key lên mạng."""
    if not GEMINI_API_KEY:
        logger.warning("Thiếu biến môi trường hoặc giá trị rỗng: GEMINI_API_KEY.")
        return False
    return True


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    if validate_config():
        logger.info("Cấu hình Azure OpenAI hợp lệ về định dạng.")
