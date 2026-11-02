"""Прикладная логика HTTP API, не зависящая от веб-фреймворка.

Методы сервиса проверяют входные данные, обращаются к слою доступа
к данным и возбуждают ApiError при ошибках клиента.
"""

import base64
import binascii
import re

from webm2mp3.report import build_report
from webm2mp3.storage import ENTITY, FEEDBACK, QUERY
from webm2mp3.tasks import STATUS_PENDING

IDENTIFIER_PATTERN = re.compile(r"[A-Za-z0-9_-]{1,64}")
TAG_SEPARATOR = ","


class ApiError(Exception):
    """Ошибка в запросе клиента."""


def check_identifier(identifier):
    """Проверяет допустимость идентификатора записи."""
    if not IDENTIFIER_PATTERN.fullmatch(identifier):
        raise ApiError(f"недопустимый идентификатор: {identifier!r}")
    return identifier


def require_text(mapping, key):
    """Возвращает обязательное непустое строковое поле."""
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ApiError(f"поле {key} должно быть непустой строкой")
    return value


def optional_text(mapping, key):
    """Возвращает необязательное строковое поле (по умолчанию пустое)."""
    value = mapping.get(key, "")
    if not isinstance(value, str):
        raise ApiError(f"поле {key} должно быть строкой")
    return value


def check_tags(tags):
    """Проверяет, что теги - список непустых строк без запятых."""
    if not isinstance(tags, list):
        raise ApiError("поле tags должно быть списком строк")
    for tag in tags:
        if not isinstance(tag, str) or not tag or TAG_SEPARATOR in tag:
            raise ApiError(f"недопустимый тег: {tag!r}")
    return tags


def parse_tags(text):
    """Разбирает теги, перечисленные через запятую в строке запроса."""
    return [tag for tag in text.split(TAG_SEPARATOR) if tag]


def decode_source(mapping):
    """Декодирует содержимое файла WebM из поля source в Base64."""
    source = require_text(mapping, "source")
    try:
        return base64.b64decode(source, validate=True)
    except binascii.Error as error:
        raise ApiError("поле source должно быть в Base64") from error


def pick(mapping, keys):
    """Выбирает из отображения только перечисленные ключи."""
    return {key: mapping[key] for key in keys if key in mapping}


class Service:
    """Операции над таблицами Entity, Query, Feedback и отчётом."""

    def __init__(self, storage, runner, clock):
        """Связывает сервис с хранилищем, исполнителем задач и часами."""
        self.storage = storage
        self.runner = runner
        self.clock = clock

    def save_entity(self, identifier, body):
        """Создаёт запись Entity."""
        check_identifier(identifier)
        record = {"identifier": identifier, "name": require_text(body, "name")}
        if not self.storage.insert(ENTITY, record):
            raise ApiError(f"Entity {identifier} уже существует")
        return record

    def delete_entity(self, body):
        """Удаляет Entity вместе с её запросами и их результатами."""
        identifier = require_text(body, "identifier")
        if not self.storage.delete(ENTITY, identifier):
            raise ApiError(f"Entity {identifier} не найдена")
        for query in self.storage.select(QUERY, {"entity": identifier}):
            self._drop_query(query["identifier"])
        return {"identifier": identifier}

    def show_entity(self, args):
        """Ищет записи Entity по полям identifier и name."""
        return self.storage.select(ENTITY, pick(args, ("identifier", "name")))

    def renew_entity(self, args):
        """Изменяет имя записи Entity."""
        identifier = require_text(args, "identifier")
        changes = {"name": require_text(args, "name")}
        return self._update(ENTITY, identifier, changes)

    def save_query(self, identifier, body):
        """Создаёт запрос Query и запускает задачу извлечения звука."""
        check_identifier(identifier)
        record = {
            "identifier": identifier,
            "entity": require_text(body, "entity"),
            "datetime": self.clock().isoformat(),
            "description": optional_text(body, "description"),
            "tags": check_tags(body.get("tags", [])),
        }
        data = decode_source(body)
        if not self.storage.select(ENTITY, {"identifier": record["entity"]}):
            raise ApiError(f"Entity {record['entity']} не найдена")
        if not self.storage.insert(QUERY, record):
            raise ApiError(f"Query {identifier} уже существует")
        feedback = {"query": identifier, "status": STATUS_PENDING,
                    "response": None}
        self.storage.insert(FEEDBACK, feedback)
        self.runner.submit(identifier, data)
        return record

    def delete_query(self, body):
        """Удаляет запрос Query вместе с его результатом."""
        identifier = require_text(body, "identifier")
        if not self._drop_query(identifier):
            raise ApiError(f"Query {identifier} не найден")
        return {"identifier": identifier}

    def show_query(self, entity, args):
        """Ищет запросы Entity по полю identifier и тегу tag."""
        filters = {"entity": entity, **pick(args, ("identifier",))}
        queries = self.storage.select(QUERY, filters)
        if "tag" in args:
            queries = [q for q in queries if args["tag"] in q["tags"]]
        return queries

    def renew_query(self, args):
        """Изменяет описание и теги запроса Query."""
        identifier = require_text(args, "identifier")
        changes = pick(args, ("description",))
        if "tags" in args:
            changes["tags"] = parse_tags(args["tags"])
        return self._update(QUERY, identifier, changes)

    def show_feedback(self, query, args):
        """Ищет результаты запроса Query по полю status."""
        filters = {"query": query, **pick(args, ("status",))}
        return self.storage.select(FEEDBACK, filters)

    def show_report(self):
        """Строит отчёт по формуле (11)."""
        queries = self.storage.select(QUERY, {})
        feedback = self.storage.select(FEEDBACK, {})
        return build_report(queries, feedback, self.clock())

    def _update(self, table, identifier, changes):
        """Изменяет запись или возбуждает ApiError, если её нет."""
        record = self.storage.update(table, identifier, changes)
        if record is None:
            raise ApiError(f"запись {identifier} не найдена")
        return record

    def _drop_query(self, identifier):
        """Удаляет запрос и его результат; True, если запрос был."""
        self.storage.delete(FEEDBACK, identifier)
        return self.storage.delete(QUERY, identifier)
