"""Построение отчёта Report по формуле (11) варианта.

Отчёт - проекция на поля F.response, Q.description и Q.tags полного
внешнего соединения запросов Q, созданных менее 9 минут назад, с
результатами F по условию Q.identifier = F.query.
"""

import json
from datetime import datetime, timedelta

REPORT_WINDOW = timedelta(minutes=9)


def full_outer_join(left, right, left_key, right_key):
    """Возвращает пары записей полного внешнего соединения.

    Для записи без пары на месте отсутствующей стороны стоит None.
    """
    index = {}
    for row in right:
        index.setdefault(row[right_key], []).append(row)
    pairs = []
    matched = set()
    for row in left:
        partners = index.get(row[left_key], [])
        matched.update(id(partner) for partner in partners)
        pairs.extend((row, partner) for partner in partners or [None])
    pairs.extend((None, row) for row in right if id(row) not in matched)
    return pairs


def project(query, feedback):
    """Проекция пары записей на поля отчёта."""
    query = query or {}
    feedback = feedback or {}
    return {
        "response": feedback.get("response"),
        "description": query.get("description"),
        "tags": query.get("tags"),
    }


def distinct(rows):
    """Удаляет повторяющиеся строки с сохранением порядка."""
    unique = {}
    for row in rows:
        unique.setdefault(json.dumps(row, sort_keys=True), row)
    return list(unique.values())


def build_report(queries, feedback, now):
    """Строит отчёт по формуле (11) на момент времени now."""
    threshold = now - REPORT_WINDOW
    recent = [
        query for query in queries
        if datetime.fromisoformat(query["datetime"]) > threshold
    ]
    pairs = full_outer_join(recent, feedback, "identifier", "query")
    return distinct(project(query, item) for query, item in pairs)
