"""Тесты асинхронного выполнения задач извлечения звука."""

from datetime import datetime, timezone
from pathlib import Path

from webm2mp3 import tasks
from webm2mp3.storage import FEEDBACK, QUERY, MemoryStorage
from webm2mp3.tasks import STATUS_DONE, STATUS_FAILED, TaskRunner

MP3_SIGNATURE = b"ID3"
QUERY_ID = 7


def clock():
    """Фиксированные часы."""
    return datetime(2026, 11, 3, tzinfo=timezone.utc)


def run_task(tmp_path, data, parameter=None, keep_query=True):
    """Выполняет одну задачу в реальном режиме.

    Возвращает итоговый Query и список записей Feedback.
    """
    storage = MemoryStorage()
    if keep_query:
        storage.insert(QUERY, {"identifier": QUERY_ID, "status": "pending"})
    runner = TaskRunner(storage, tmp_path / "out", clock)
    runner.submit(QUERY_ID, data, parameter).result()
    runner.shutdown()
    queries = storage.select(QUERY, {})
    return queries, storage.select(FEEDBACK, {"query": QUERY_ID})


def test_conversion_creates_mp3(tmp_path, samples):
    """Успешная задача сохраняет MP3 и путь к нему в Feedback."""
    queries, feedback = run_task(tmp_path, samples[4].read_bytes(), "96k")
    assert queries[0]["status"] == STATUS_DONE
    assert len(feedback) == 1
    item = feedback[0]
    assert item["status"] == STATUS_DONE
    assert item["failure"] is None
    assert item["datetime"] == int(clock().timestamp())
    assert Path(item["response"]).read_bytes().startswith(MP3_SIGNATURE)


def test_conversion_failure(tmp_path):
    """Ошибка утилиты записывается в поле failure."""
    queries, feedback = run_task(tmp_path, b"not a webm file")
    assert queries[0]["status"] == STATUS_FAILED
    assert feedback[0]["status"] == STATUS_FAILED
    assert feedback[0]["response"] is None
    assert feedback[0]["failure"]


def test_parameter_sets_bitrate(tmp_path, samples):
    """Параметр запроса передаётся утилите как битрейт MP3."""
    data = samples[1].read_bytes()
    _, low = run_task(tmp_path / "low", data, "32k")
    _, high = run_task(tmp_path / "high", data, "320k")
    low_size = Path(low[0]["response"]).stat().st_size
    high_size = Path(high[0]["response"]).stat().st_size
    assert low_size < high_size


def test_missing_interpreter(tmp_path, monkeypatch):
    """Невозможность запустить процесс отражается в Feedback."""
    monkeypatch.setattr(tasks, "cli_command", lambda _: ["no-such-program"])
    _, feedback = run_task(tmp_path, b"data")
    assert feedback[0]["status"] == STATUS_FAILED


def test_deleted_query_gets_no_feedback(tmp_path):
    """Если запрос удалён до завершения задачи, Feedback не создаётся."""
    queries, feedback = run_task(tmp_path, b"data", keep_query=False)
    assert queries == []
    assert feedback == []
