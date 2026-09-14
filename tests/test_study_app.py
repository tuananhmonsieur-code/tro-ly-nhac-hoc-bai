"""Kiểm tra không gọi mạng, không hiện popup và không chạm database sử dụng thật."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing, redirect_stdout
from datetime import datetime
import io
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
from threading import Event
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import httpx
from openai import AzureOpenAI

# Import không đọc .env thật. Các test AI cũng thay toàn bộ cấu hình bằng dữ liệu giả.
with patch("dotenv.load_dotenv", return_value=False):
    import ai_engine
    import config
    import database
    import main
    import notifier
    import scheduler


ROOT = Path(__file__).resolve().parents[1]


class FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        value = cls(2026, 9, 15, 23, 59, 42)
        return value if tz is None else value.astimezone(tz)


class DatabaseFixture(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory(prefix=".test-", dir=ROOT)
        assert Path(scratch.name).resolve().is_relative_to(ROOT.resolve())
        self.addCleanup(scratch.cleanup)
        self.path = Path(scratch.name) / "tasks.db"
        self.enterContext(patch.object(database, "DB_PATH", self.path))
        self.enterContext(patch.object(database, "datetime", FixedDatetime))
        database.init_db()


class DatabaseTests(DatabaseFixture):
    def test_current_minute_is_due_and_completed_is_not_due(self):
        task_id = database.add_task("  Toán   học  ", "23:59")
        tasks = database.get_due_tasks("2026-09-15 23:59:42")
        self.assertEqual(tasks, [{"id": task_id, "subject": "Toán học",
                                 "study_time": "2026-09-15 23:59:00", "status": "pending"}])
        database.mark_task_completed(task_id)
        self.assertEqual(database.get_due_tasks("2026-09-16 01:00:00"), [])
        self.assertEqual(database.get_all_tasks()[0]["status"], "completed")

    def test_midnight_rollover_and_overdue_recovery(self):
        late = database.add_task("Lý", "23:58")
        early = database.add_task("Hóa", "00:01")
        now = database.add_task("Toán", "23:59")
        self.assertEqual([t["id"] for t in database.get_all_tasks()], [now, early, late])
        self.assertEqual([t["id"] for t in database.get_due_tasks("2026-09-16 00:00:00")], [now])
        self.assertEqual([t["id"] for t in database.get_due_tasks("2026-09-16 00:01:00")], [now, early])
        self.assertEqual(database.get_all_tasks()[-1]["study_time"], "2026-09-16 23:58:00")

    def test_invalid_input_does_not_insert(self):
        for subject, hour in [(" ", "12:00"), ("Toán", "24:00"), ("Toán", "9:00"),
                              ("Toán", "10:60"), ("Toán", "12:00:00"), (None, "12:00")]:
            with self.subTest(subject=subject, hour=hour), self.assertRaises(ValueError):
                database.add_task(subject, hour)
        self.assertEqual(database.get_all_tasks(), [])
        with self.assertRaises(ValueError):
            database.get_due_tasks("2026-02-30 12:00:00")

    def test_sql_text_is_stored_as_data_and_connections_close(self):
        subject = "Toán'); DROP TABLE tasks; --"
        task_id = database.add_task(subject, "23:59")
        database.init_db()
        self.assertEqual(database.get_all_tasks()[0]["subject"], subject)
        database.mark_task_completed(task_id)
        # Windows không cho đổi tên database nếu còn connection mở.
        renamed = self.path.with_suffix(".renamed")
        self.path.rename(renamed)
        renamed.rename(self.path)

    def test_database_errors_propagate(self):
        with patch.object(database.sqlite3, "connect", side_effect=sqlite3.OperationalError):
            with self.assertRaises(sqlite3.Error):
                database.get_all_tasks()
            with self.assertRaises(sqlite3.Error):
                database.add_task("Toán", "23:59")
        with self.assertRaises(ValueError):
            database.mark_task_completed(999)

    def test_legacy_schedule_is_rejected_without_mutation(self):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("INSERT INTO tasks VALUES (1, 'Toán', '12:00', 'pending')")
        with self.assertRaises(ValueError):
            database.init_db()
        self.assertEqual(database.get_all_tasks()[0]["study_time"], "12:00")

    def test_separate_threads_can_add_tasks(self):
        with ThreadPoolExecutor(max_workers=4) as pool:
            ids = list(pool.map(lambda n: database.add_task(f"Môn {n}", "23:59"), range(8)))
        self.assertEqual(len(set(ids)), 8)
        self.assertEqual(len(database.get_all_tasks()), 8)


class SchedulerFlowTests(DatabaseFixture):
    def test_success_is_not_sent_twice(self):
        database.add_task("Toán", "23:59")
        with patch.object(scheduler, "datetime", FixedDatetime), \
             patch.object(ai_engine, "generate_reminder", return_value="Lời nhắc"), \
             patch.object(notifier, "send_desktop_notification", return_value=True) as send:
            scheduler.check_and_notify()
            scheduler.check_and_notify()
        self.assertEqual(send.call_count, 1)
        self.assertEqual(database.get_all_tasks()[0]["status"], "completed")

    def test_notification_failure_retries_pending_task(self):
        database.add_task("Toán", "23:59")
        with patch.object(scheduler, "datetime", FixedDatetime), \
             patch.object(ai_engine, "generate_reminder", return_value="Lời nhắc"), \
             patch.object(notifier, "send_desktop_notification", side_effect=[False, True]) as send:
            scheduler.check_and_notify()
            self.assertEqual(database.get_all_tasks()[0]["status"], "pending")
            scheduler.check_and_notify()
        self.assertEqual(send.call_count, 2)
        self.assertEqual(database.get_all_tasks()[0]["status"], "completed")

    def test_one_broken_task_does_not_block_the_next(self):
        database.add_task("Toán", "23:59")
        database.add_task("Lý", "23:59")
        with patch.object(scheduler, "datetime", FixedDatetime), \
             patch.object(ai_engine, "generate_reminder", side_effect=[RuntimeError, "Lời nhắc"]), \
             patch.object(notifier, "send_desktop_notification", return_value=True):
            scheduler.check_and_notify()
        self.assertEqual([t["status"] for t in database.get_all_tasks()], ["pending", "completed"])

    def test_missing_ai_configuration_still_sends_fallback(self):
        database.add_task("Toán", "23:59")
        with patch.object(scheduler, "datetime", FixedDatetime), \
             patch.object(config, "validate_config", return_value=False), \
             patch.object(ai_engine, "AzureOpenAI") as client, \
             patch.object(notifier, "send_desktop_notification", return_value=True) as send:
            scheduler.check_and_notify()
        client.assert_not_called()
        self.assertEqual(len(send.call_args.args[1].splitlines()), 4)
        self.assertEqual(database.get_all_tasks()[0]["status"], "completed")

    def test_failed_read_releases_lock_for_next_run(self):
        with patch.object(database, "get_due_tasks", side_effect=[sqlite3.OperationalError, []]) as read:
            scheduler.check_and_notify()
            scheduler.check_and_notify()
        self.assertEqual(read.call_count, 2)


class AITests(unittest.TestCase):
    def setUp(self):
        self.enterContext(patch.object(config, "validate_config", return_value=True))
        for name, value in {
            "AZURE_OPENAI_API_KEY": secrets.token_urlsafe(24),
            "AZURE_OPENAI_ENDPOINT": "https://example.invalid",
            "AZURE_OPENAI_DEPLOYMENT_NAME": "test-deployment",
            "AZURE_OPENAI_API_VERSION": "test-version",
        }.items():
            self.enterContext(patch.object(config, name, value))

    def test_sdk_request_and_response_with_mock_http_transport(self):
        expected = "Học Toán nhé!\n1. Mở sách.\n2. Ôn ý chính.\n3. Làm bài ngắn."
        requests = []

        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={
                "id": "test-completion", "object": "chat.completion", "created": 0,
                "model": "test-deployment", "choices": [{"index": 0, "finish_reason": "stop",
                "message": {"role": "assistant", "content": expected}}],
            })

        def client_factory(**kwargs):
            return AzureOpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(respond)))

        with patch.object(ai_engine, "AzureOpenAI", side_effect=client_factory):
            self.assertEqual(ai_engine.generate_reminder("Toán"), expected)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].url.path, "/openai/deployments/test-deployment/chat/completions")
        self.assertEqual(requests[0].url.params["api-version"], "test-version")
        body = json.loads(requests[0].content)
        self.assertEqual(body["model"], "test-deployment")
        self.assertEqual(body["messages"][0]["role"], "system")

    def test_sdk_error_is_redacted_and_returns_fallback(self):
        marker = secrets.token_urlsafe(24)
        with patch.object(ai_engine, "AzureOpenAI", side_effect=RuntimeError(marker)), \
             self.assertLogs("ai_engine", level="WARNING") as logs:
            reminder = ai_engine.generate_reminder("Toán")
        self.assertEqual(len(reminder.splitlines()), 4)
        self.assertNotIn(marker, " ".join(logs.output))

    def test_empty_malformed_or_long_content_uses_complete_fallback(self):
        for content in (None, "", "Chỉ một dòng", "x" * 300):
            with self.subTest(content=content), patch.object(ai_engine, "AzureOpenAI") as factory:
                factory.return_value.__enter__.return_value.chat.completions.create.return_value = \
                    SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])
                reminder = ai_engine.generate_reminder("Tên môn rất dài " * 30)
            self.assertEqual(len(reminder.splitlines()), 4)
            self.assertLessEqual(len(reminder.encode("utf-16-le")) // 2, 240)
            self.assertLessEqual(len(reminder.splitlines()[0].split()), 30)


class NotifierTests(unittest.TestCase):
    def test_backend_success_and_failure(self):
        backend = SimpleNamespace(notification=MagicMock())
        with patch.dict("sys.modules", {"plyer": backend}):
            self.assertTrue(notifier.send_desktop_notification("Học bài", "Mở sách nhé!"))
            backend.notification.notify.assert_called_once_with(
                title="Học bài", message="Mở sách nhé!", timeout=10
            )
            backend.notification.notify.side_effect = NotImplementedError
            self.assertFalse(notifier.send_desktop_notification("Học bài", "Lời nhắc"))

    def test_windows_buffer_limits_do_not_split_surrogate_pairs(self):
        backend = SimpleNamespace(notification=MagicMock())
        with patch.dict("sys.modules", {"plyer": backend}), patch.object(notifier.sys, "platform", "win32"):
            self.assertTrue(notifier.send_desktop_notification("📚" * 100, "📚" * 300))
        values = backend.notification.notify.call_args.kwargs
        self.assertLessEqual(len(values["title"].encode("utf-16-le")) // 2, 63)
        self.assertLessEqual(len(values["message"].encode("utf-16-le")) // 2, 255)


class LifecycleTests(unittest.TestCase):
    def test_actual_scheduler_runs_once_on_start_and_is_reused(self):
        called = Event()
        with patch.object(scheduler, "_scheduler", None), \
             patch.object(scheduler, "check_and_notify", side_effect=called.set) as check:
            instance = scheduler.start_scheduler()
            try:
                self.assertIs(scheduler.start_scheduler(), instance)
                self.assertTrue(called.wait(3), "Job không chạy khi khởi động")
                self.assertEqual(check.call_count, 1)
                self.assertEqual(len(instance.get_jobs()), 1)
                job = instance.get_job(scheduler.JOB_ID)
                self.assertEqual(job.trigger.interval.total_seconds(), 60)
                self.assertEqual(job.max_instances, 1)
                self.assertTrue(job.coalesce)
            finally:
                instance.shutdown(wait=True)
            self.assertFalse(instance.running)

    def test_cli_add_list_and_exit(self):
        background = MagicMock()
        output = io.StringIO()
        with patch.object(main, "_configure_logging"), \
             patch.object(config, "validate_config", return_value=False), \
             patch.object(database, "init_db"), \
             patch.object(scheduler, "start_scheduler", return_value=background), \
             patch.object(database, "add_task", return_value=7) as add, \
             patch.object(database, "get_all_tasks", return_value=[{
                 "id": 7, "subject": "Toán", "study_time": "2026-09-16 08:00:00", "status": "pending"}]), \
             patch("builtins.input", side_effect=["1", "Toán", "08:00", "2", "3"]), \
             patch.object(main.time, "sleep"), redirect_stdout(output):
            main.main()
        add.assert_called_once_with("Toán", "08:00")
        self.assertIn("2026-09-16 08:00:00", output.getvalue())
        background.shutdown.assert_called_once_with(wait=True)

    def test_cli_eof_and_ctrl_c_shutdown(self):
        for error in (EOFError, KeyboardInterrupt):
            with self.subTest(error=error):
                background = MagicMock()
                with patch.object(main, "_configure_logging"), \
                     patch.object(config, "validate_config", return_value=False), \
                     patch.object(database, "init_db"), \
                     patch.object(scheduler, "start_scheduler", return_value=background), \
                     patch("builtins.input", side_effect=error), redirect_stdout(io.StringIO()):
                    main.main()
                background.shutdown.assert_called_once_with(wait=True)

    def test_cli_startup_failure_does_not_enter_menu(self):
        with patch.object(main, "_configure_logging"), \
             patch.object(config, "validate_config", return_value=False), \
             patch.object(database, "init_db", side_effect=sqlite3.OperationalError), \
             patch.object(scheduler, "start_scheduler") as start, \
             patch("builtins.input") as prompt, redirect_stdout(io.StringIO()):
            main.main()
        start.assert_not_called()
        prompt.assert_not_called()


if __name__ == "__main__":
    unittest.main()
