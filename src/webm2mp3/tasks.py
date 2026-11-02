"""Асинхронное выполнение задач извлечения звука.

Каждая задача запускает утилиту командной строки webm2mp3 в
отдельном процессе средствами модуля subprocess. Ход выполнения
отражается в поле status запроса Query, а итог записывается новой
записью таблицы Feedback.
"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from webm2mp3.cli import DEFAULT_BITRATE, EXIT_OK
from webm2mp3.storage import FEEDBACK, QUERY

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_DONE = "done"
STATUS_FAILED = "failed"
DEFAULT_WORKERS = 2
DEFAULT_TIMEOUT = 600


def cli_command(bitrate):
    """Команда запуска утилиты командной строки webm2mp3."""
    return [sys.executable, "-m", "webm2mp3.cli", "--bitrate", bitrate]


def stub_response(data):
    """Ответ задачи в тестовом режиме без реальной конвертации."""
    return f"test-mode: {len(data)} bytes"


def timestamp(clock):
    """Текущее Unix-время по часам clock в целых секундах."""
    return int(clock().timestamp())


class TaskRunner:
    """Исполнитель задач извлечения звука в пуле потоков."""

    def __init__(self, storage, output_dir, clock, test_mode=False,
                 workers=DEFAULT_WORKERS):
        """Создаёт исполнитель.

        В тестовом режиме задача завершается сразу, без запуска
        утилиты, а пул потоков не создаётся.
        """
        self._storage = storage
        self._output_dir = Path(output_dir)
        self._clock = clock
        self._test_mode = test_mode
        self._executor = None
        if not test_mode:
            self._executor = ThreadPoolExecutor(max_workers=workers)

    def submit(self, identifier, data, parameter=None):
        """Ставит задачу в очередь; возвращает Future или None.

        Параметр parameter задаёт битрейт MP3, например 128k.
        """
        if self._test_mode:
            self._finish(identifier, STATUS_DONE, stub_response(data))
            return None
        bitrate = parameter or DEFAULT_BITRATE
        return self._executor.submit(self._convert, identifier, data,
                                     bitrate)

    def shutdown(self):
        """Дожидается завершения запущенных задач."""
        if self._executor is not None:
            self._executor.shutdown(wait=True)

    def _finish(self, identifier, status, response=None, failure=None):
        """Сохраняет итог задачи, если запрос ещё не удалён."""
        changes = {"status": status}
        if self._storage.update(QUERY, identifier, changes) is None:
            return
        self._storage.insert_auto(FEEDBACK, {
            "datetime": timestamp(self._clock),
            "response": response,
            "status": status,
            "failure": failure,
            "query": identifier,
        })

    def _convert(self, identifier, data, bitrate):
        """Запускает утилиту и сохраняет полученный MP3 на диск."""
        self._storage.update(QUERY, identifier, {"status": STATUS_RUNNING})
        try:
            result = subprocess.run(
                cli_command(bitrate), input=data, capture_output=True,
                timeout=DEFAULT_TIMEOUT, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            self._finish(identifier, STATUS_FAILED, failure=str(error))
            return
        if result.returncode != EXIT_OK:
            message = result.stderr.decode("utf-8", errors="replace")
            self._finish(identifier, STATUS_FAILED, failure=message.strip())
            return
        self._output_dir.mkdir(parents=True, exist_ok=True)
        target = self._output_dir / f"{identifier}.mp3"
        target.write_bytes(result.stdout)
        self._finish(identifier, STATUS_DONE, str(target.resolve()))
