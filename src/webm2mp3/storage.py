"""Слой доступа к данным: таблицы Entity, Query и Feedback.

Хранилище предоставляет операции над таблицами: вставку (в том числе
с автоматическим идентификатором), удаление, поиск и изменение.
Ключевое поле каждой таблицы - целочисленный identifier.
"""

import copy
import threading

ENTITY = "entity"
QUERY = "query"
FEEDBACK = "feedback"
TABLES = (ENTITY, QUERY, FEEDBACK)
KEY = "identifier"


def matches(record, filters):
    """Проверяет, что запись содержит все пары поле-значение фильтра."""
    return all(record.get(key) == value for key, value in filters.items())


class MemoryStorage:
    """Потокобезопасное хранилище записей в оперативной памяти."""

    def __init__(self):
        """Создаёт пустые таблицы."""
        self._tables = {table: {} for table in TABLES}
        self._lock = threading.Lock()

    def insert(self, table, record):
        """Добавляет запись; возвращает False, если ключ уже занят."""
        with self._lock:
            rows = self._tables[table]
            if record[KEY] in rows:
                return False
            rows[record[KEY]] = copy.deepcopy(record)
            return True

    def insert_auto(self, table, record):
        """Добавляет запись с идентификатором на 1 больше максимального."""
        with self._lock:
            rows = self._tables[table]
            row = {KEY: max(rows, default=0) + 1, **copy.deepcopy(record)}
            rows[row[KEY]] = row
            return copy.deepcopy(row)

    def delete(self, table, key):
        """Удаляет запись по ключу; возвращает True, если она была."""
        with self._lock:
            return self._tables[table].pop(key, None) is not None

    def select(self, table, filters):
        """Возвращает копии записей, удовлетворяющих фильтру."""
        with self._lock:
            rows = self._tables[table].values()
            return [
                copy.deepcopy(row) for row in rows if matches(row, filters)
            ]

    def update(self, table, key, changes):
        """Изменяет поля записи; возвращает её новую версию или None."""
        with self._lock:
            row = self._tables[table].get(key)
            if row is None:
                return None
            row.update(copy.deepcopy(changes))
            return copy.deepcopy(row)

    def close(self):
        """Освобождает ресурсы хранилища."""
