"""Запуск веб-приложения с HTTP API из командной строки.

Имя пользователя и пароль HTTP API передаются как аргументы
командной строки: --username и --password.
"""

import argparse
from datetime import datetime, timezone

from webm2mp3.app import create_app
from webm2mp3.service import Service
from webm2mp3.storage import MemoryStorage
from webm2mp3.tasks import DEFAULT_WORKERS, TaskRunner

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8080
DEFAULT_OUTPUT_DIR = "data/output"


def utc_now():
    """Текущее время в часовом поясе UTC."""
    return datetime.now(timezone.utc)


def parse_args(argv):
    """Разбирает аргументы командной строки сервера."""
    parser = argparse.ArgumentParser(
        prog="webm2mp3-server",
        description="HTTP API для асинхронного извлечения MP3 из WebM.",
    )
    parser.add_argument("--username", required=True,
                        help="имя пользователя HTTP API")
    parser.add_argument("--password", required=True,
                        help="пароль HTTP API")
    parser.add_argument("--host", default=DEFAULT_HOST,
                        help="адрес сервера (по умолчанию %(default)s)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT,
                        help="порт сервера (по умолчанию %(default)s)")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR,
                        help="папка для MP3 (по умолчанию %(default)s)")
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS,
                        help="число параллельных задач")
    parser.add_argument("--test-mode", action="store_true",
                        help="не выполнять реальную конвертацию")
    return parser.parse_args(argv)


def build_storage(args):
    """Создаёт слой доступа к данным по аргументам командной строки."""
    return MemoryStorage()


def build_app(args):
    """Собирает приложение Flask и исполнитель задач."""
    storage = build_storage(args)
    runner = TaskRunner(storage, args.output_dir, args.test_mode,
                        args.workers)
    service = Service(storage, runner, utc_now)
    return create_app(service, args.username, args.password), runner


def main(argv=None):
    """Точка входа сервера."""
    args = parse_args(argv)
    app, runner = build_app(args)
    try:
        app.run(host=args.host, port=args.port, threaded=True)
    finally:
        runner.shutdown()


if __name__ == "__main__":
    main()
