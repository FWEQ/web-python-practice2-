"""Пример работы с HTTP API через ApiClient.

Отправляет файлы WebM на запущенный сервер, дожидается завершения
задач и печатает результаты и отчёт. Использование:
python examples/client_demo.py URL USERNAME PASSWORD FILE.webm...
"""

import sys
import time
from pathlib import Path

from webm2mp3.client import ApiClient
from webm2mp3.tasks import STATUS_PENDING, STATUS_RUNNING

POLL_SECONDS = 0.5
ACTIVE = (STATUS_PENDING, STATUS_RUNNING)


def wait_feedback(client, query):
    """Опрашивает Feedback, пока задача не завершится."""
    while True:
        feedback = client.show_feedback(query).payload["result"][0]
        if feedback["status"] not in ACTIVE:
            return feedback
        time.sleep(POLL_SECONDS)


def main(argv=None):
    """Точка входа демонстрационного клиента."""
    url, username, password, *files = sys.argv[1:] if argv is None else argv
    client = ApiClient(url, username, password)
    print(client.save_entity("demo", "Демонстрация").payload)
    queries = []
    for number, name in enumerate(files, start=1):
        path = Path(name)
        identifier = f"q{number}"
        response = client.save_query(identifier, "demo", path.read_bytes(),
                                     path.name, ["demo"])
        print(response.payload)
        queries.append(identifier)
    for identifier in queries:
        print(wait_feedback(client, identifier))
    print(client.show_report().payload)


if __name__ == "__main__":
    main()
