"""Асинхронное выполнение задач извлечения звука.

Каждая задача запускает утилиту командной строки webm2mp3 в
отдельном процессе средствами модуля subprocess. Ход выполнения
отражается в записи таблицы Feedback, связанной с запросом.
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from webm2mp3.cli import EXIT_OK
from webm2mp3.storage import FEEDBACK

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
DEFAULT_WORKERS = 2
DEFAULT_TIMEOUT = 600


def cli_command():
    """Команда запуска утилиты командной строки webm2mp3."""
    return [sys.executable, "-m", "webm2mp3.cli"]


def stub_response(data):
    """Ответ задачи в тестовом режиме без реальной конвертации."""
    return f"test-mode: {len(data)} bytes"


class TaskRunner:
    """Исполнитель задач извлечения звука в пуле потоков."""

    def __init__(self, storage, output_dir, test_mode=False,
                 workers=DEFAULT_WORKERS):
        """Создаёт исполнитель.

        В тестовом режиме задача завершается сразу, без запуска
        утилиты, а пул потоков не создаётся.
        """
        self._storage = storage
        self._output_dir = Path(output_dir)
        self._test_mode = test_mode
        self._executor = None
        if not test_mode:
            self._executor = ThreadPoolExecutor(max_workers=workers)

    def submit(self, identifier, data):
        """Ставит задачу в очередь; возвращает Future или None."""
        if self._test_mode:
            self._finish(identifier, STATUS_DONE, stub_response(data))
            return None
        return self._executor.submit(self._convert, identifier, data)

    def shutdown(self):
        """Дожидается завершения запущенных задач."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)

    def _finish(self, identifier, status, response):
        """Сохраняет итог задачи в таблицу Feedback."""
        changes = {"status": status, "response": response}
        self._storage.update(FEEDBACK, identifier, changes)

    def _convert(self, identifier, data):
        """Запускает утилиту и сохраняет полученный MP3 на диск."""
        self._storage.update(FEEDBACK, identifier, {"status": STATUS_RUNNING})
        try:
            result = subprocess.run(
                cli_command(), input=data, capture_output=True,
                timeout=DEFAULT_TIMEOUT, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self._finish(identifier, STATUS_FAILED, str(error))
            return
        if result.returncode != EXIT_OK:
            message = result.stderr.decode("utf-8", errors="replace")
            self._finish(identifier, STATUS_FAILED, message.strip())
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)
        target = self._output_dir / f"{identifier}.mp3"
        target.write_bytes(result.stdout)
        self._finish(identifier, STATUS_DONE, str(target.resolve()))
