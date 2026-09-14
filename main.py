"""Chạy bằng python main.py; giữ cửa sổ console mở để nhận lời nhắc."""

import logging
import sqlite3
import time

import config
import database
import scheduler


logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Log HTTP/SDK có thể chứa endpoint hoặc headers. Chỉ dùng log lỗi đã làm sạch.
    prefixes = ("openai", "httpx", "httpcore", "httpx2")
    for name in set(logging.root.manager.loggerDict) | set(prefixes):
        if any(name == prefix or name.startswith(prefix + ".") for prefix in prefixes):
            logging.getLogger(name).setLevel(logging.CRITICAL + 1)
    logging.getLogger("apscheduler").setLevel(logging.WARNING)


def _show_tasks() -> None:
    tasks = database.get_all_tasks()
    if not tasks:
        print("Chưa có lịch học. Chọn 1 để thêm môn học.")
        return
    print("\nLỊCH HỌC — giờ địa phương của máy")
    for task in tasks:
        status = "Chờ nhắc" if task["status"] == "pending" else "Đã gửi nhắc"
        print(f"#{task['id']} | {task['study_time']} | {task['subject']} | {status}")
    print("'Đã gửi nhắc' không có nghĩa là bạn đã học xong.")


def main() -> None:
    _configure_logging()
    background = None
    try:
        print("TRỢ LÝ AI NHẮC HỌC BÀI")
        if not config.validate_config():
            print("AI chưa được cấu hình đầy đủ; ứng dụng sẽ dùng lời nhắc mặc định.")
        try:
            database.init_db()
            background = scheduler.start_scheduler()
        except Exception as exc:
            logger.error("Không thể mở ứng dụng (%s).", type(exc).__name__)
            print("Khởi động thất bại. Kiểm tra thông báo lỗi phía trên rồi thử lại.")
            return

        print("Lịch nhắc một lần. Giờ đã qua được đặt vào ngày mai.")
        print("Giữ cửa sổ này mở; thoát chương trình sẽ dừng nhắc học.")
        while True:
            print("\n[1] Thêm môn học & giờ học (HH:MM)")
            print("[2] Xem danh sách lịch học")
            print("[3] Thoát")
            choice = input("Chọn: ").strip()
            try:
                if choice == "1":
                    subject = input("Tên môn học: ")
                    study_time = input("Giờ học (HH:MM): ").strip()
                    task_id = database.add_task(subject, study_time)
                    print(f"Đã lưu lịch #{task_id}. Chọn 2 để xem ngày giờ cụ thể.")
                elif choice == "2":
                    _show_tasks()
                elif choice == "3":
                    break
                else:
                    print("Vui lòng chọn 1, 2 hoặc 3.")
            except ValueError:
                print("Dữ liệu không hợp lệ: nhập tên môn và giờ HH:MM từ 00:00 đến 23:59.")
            except sqlite3.Error:
                print("Không thể thao tác với lịch học. Kiểm tra quyền truy cập database.")
            time.sleep(1)
    except (KeyboardInterrupt, EOFError):
        print("\nĐang thoát chương trình...")
    finally:
        if background is not None:
            try:
                background.shutdown(wait=True)
            except Exception as exc:
                logger.error("Không thể đóng scheduler (%s).", type(exc).__name__)
        print("Ứng dụng đã đóng. Nhắc học sẽ tiếp tục khi bạn mở lại.")


if __name__ == "__main__":
    main()
