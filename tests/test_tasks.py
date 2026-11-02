"""Тесты асинхронного выполнения задач извлечения звука."""

from pathlib import Path

from webm2mp3 import tasks
from webm2mp3.storage import FEEDBACK, MemoryStorage
from webm2mp3.tasks import STATUS_DONE, STATUS_FAILED, TaskRunner

MP3_SIGNATURE = b"ID3"


def run_task(tmp_path, data):
    """Выполняет одну задачу в реальном режиме и возвращает Feedback."""
    storage = MemoryStorage()
    storage.insert(FEEDBACK, {"query": "q", "status": "pending",
                              "response": None})
    runner = TaskRunner(storage, tmp_path / "out")
    runner.submit("q", data).result()
    runner.shutdown()
    return storage.select(FEEDBACK, {"query": "q"})[0]


def test_conversion_creates_mp3(tmp_path, samples):
    """Успешная задача сохраняет MP3 и путь к нему в Feedback."""
    feedback = run_task(tmp_path, samples[4].read_bytes())
    assert feedback["status"] == STATUS_DONE
    assert Path(feedback["response"]).read_bytes().startswith(MP3_SIGNATURE)


def test_conversion_failure(tmp_path):
    """Ошибка утилиты отражается в Feedback со статусом failed."""
    feedback = run_task(tmp_path, b"not a webm file")
    assert feedback["status"] == STATUS_FAILED
    assert feedback["response"]


def test_missing_interpreter(tmp_path, monkeypatch):
    """Невозможность запустить процесс отражается в Feedback."""
    monkeypatch.setattr(tasks, "cli_command", lambda: ["no-such-program"])
    feedback = run_task(tmp_path, b"data")
    assert feedback["status"] == STATUS_FAILED
