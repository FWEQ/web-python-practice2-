"""Слой доступа к данным на основе документ-ориентированной СУБД TinyDB.

Каждой таблице Entity, Query и Feedback соответствует таблица
TinyDB в одном файле JSON. Интерфейс совпадает с MemoryStorage.
"""

import threading
from pathlib import Path

from tinydb import Query, TinyDB, where

from webm2mp3.storage import KEY


class TinyDBStorage:
    """Потокобезопасное хранилище записей в файле TinyDB."""

    def __init__(self, path):
        """Открывает базу данных, создавая папку при необходимости."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(path, encoding="utf-8", ensure_ascii=False)
        self._lock = threading.Lock()

    def insert(self, table, record):
        """Добавляет запись; возвращает False, если ключ уже занят."""
        with self._lock:
            documents = self._db.table(table)
            if documents.contains(where(KEY) == record[KEY]):
                return False
            documents.insert(record)
            return True

    def insert_auto(self, table, record):
        """Добавляет запись с идентификатором на 1 больше максимального."""
        with self._lock:
            documents = self._db.table(table)
            keys = (document[KEY] for document in documents.all())
            row = {KEY: max(keys, default=0) + 1, **record}
            documents.insert(row)
            return row

    def delete(self, table, key):
        """Удаляет запись по ключу; возвращает True, если она была."""
        with self._lock:
            return bool(self._db.table(table).remove(where(KEY) == key))

    def select(self, table, filters):
        """Возвращает записи, удовлетворяющие фильтру."""
        with self._lock:
            documents = self._db.table(table)
            if filters:
                found = documents.search(Query().fragment(filters))
            else:
                found = documents.all()
            return [dict(document) for document in found]

    def update(self, table, key, changes):
        """Изменяет поля записи; возвращает её новую версию или None."""
        condition = where(KEY) == key
        with self._lock:
            documents = self._db.table(table)
            if not documents.update(changes, condition):
                return None
            return dict(documents.get(condition))

    def close(self):
        """Закрывает файл базы данных."""
        with self._lock:
            self._db.close()
