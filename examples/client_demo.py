"""Пример работы с HTTP API через ApiClient.

Отправляет файлы WebM на запущенный сервер, дожидается завершения
задач и печатает результаты и отчёт. Использование:
python examples/client_demo.py URL USERNAME PASSWORD FILE.webm...
"""

import sys
import time
from pathlib import Path

from webm2mp3.client import ApiClient

POLL_SECONDS = 0.5
ENTITY_ID = 1


def wait_feedback(client, query):
    """Опрашивает Feedback, пока задача не запишет результат."""
    while True:
        feedback = client.show_feedback(query).payload["result"]
        if feedback:
            return feedback
        time.sleep(POLL_SECONDS)


def main(argv=None):
    """Точка входа демонстрационного клиента."""
    url, username, password, *files = sys.argv[1:] if argv is None else argv
    client = ApiClient(url, username, password)
    print(client.save_entity(ENTITY_ID, "127.0.0.1", "ru_RU",
                             sys.platform).payload)
    queries = []
    for identifier, name in enumerate(files, start=1):
        path = Path(name)
        response = client.save_query(identifier, ENTITY_ID,
                                     path.read_bytes(), "128k", path.name,
                                     "demo")
        print(response.payload)
        queries.append(identifier)
    for identifier in queries:
        print(wait_feedback(client, identifier))
    print(client.show_report().payload)


if __name__ == "__main__":
    main()
