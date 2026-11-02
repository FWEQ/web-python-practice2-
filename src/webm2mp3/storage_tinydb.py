"""Слой доступа к данным на основе документ-ориентированной СУБД TinyDB.

Каждой таблице Entity, Query и Feedback соответствует таблица
TinyDB в одном файле JSON. Интерфейс совпадает с MemoryStorage.
"""

import threading
from pathlib import Path

from tinydb import Query, TinyDB, where

from webm2mp3.storage import KEYS


class TinyDBStorage:
    """Потокобезопасное хранилище записей в файле TinyDB."""

    def __init__(self, path):
        """Открывает базу данных, создавая папку при необходимости."""
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._db = TinyDB(path, encoding="utf-8", ensure_ascii=False)
        self._lock = threading.Lock()

    def _by_key(self, table, key):
        """Условие поиска записи по значению ключевого поля."""
        return where(KEYS[table]) == key

    def insert(self, table, record):
        """Добавляет запись; возвращает False, если ключ уже занят."""
        condition = self._by_key(table, record[KEYS[table]])
        with self._lock:
            documents = self._db.table(table)
            if documents.contains(condition):
                return False
            documents.insert(record)
            return True

    def delete(self, table, key):
        """Удаляет запись по ключу; возвращает True, если она была."""
        with self._lock:
            removed = self._db.table(table).remove(self._by_key(table, key))
            return bool(removed)

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
        condition = self._by_key(table, key)
        with self._lock:
            documents = self._db.table(table)
            if not documents.update(changes, condition):
                return None
            return dict(documents.get(condition))

    def close(self):
        """Закрывает файл базы данных."""
        with self._lock:
            self._db.close()
