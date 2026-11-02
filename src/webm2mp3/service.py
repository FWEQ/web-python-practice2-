"""Прикладная логика HTTP API, не зависящая от веб-фреймворка.

Методы сервиса проверяют входные данные, обращаются к слою доступа
к данным и возбуждают ApiError при ошибках клиента.
"""

import base64
import binascii
import re

from webm2mp3.report import build_report
from webm2mp3.storage import ENTITY, FEEDBACK, QUERY
from webm2mp3.tasks import STATUS_PENDING, timestamp

IDENTIFIER_PATTERN = re.compile(r"[0-9]{1,18}")
BITRATE_PATTERN = re.compile(r"[0-9]{1,3}k")
TAG_SEPARATOR = ","
ENTITY_FIELDS = ("ip", "locale", "platform")


class ApiError(Exception):
    """Ошибка в запросе клиента."""


def parse_identifier(text, name="identifier"):
    """Преобразует идентификатор из пути или строки запроса в число."""
    if not IDENTIFIER_PATTERN.fullmatch(text):
        raise ApiError(f"{name} должен быть целым неотрицательным числом")
    return int(text)


def require_identifier(mapping, key):
    """Возвращает обязательное целочисленное поле тела запроса."""
    value = mapping.get(key)
    if type(value) is not int or value < 0:
        raise ApiError(f"поле {key} должно быть целым неотрицательным")
    return value


def require_text(mapping, key):
    """Возвращает обязательное непустое строковое поле."""
    value = mapping.get(key)
    if not isinstance(value, str) or not value:
        raise ApiError(f"поле {key} должно быть непустой строкой")
    return value


def optional_text(mapping, key):
    """Возвращает необязательное строковое поле или None."""
    value = mapping.get(key)
    if value is not None and not isinstance(value, str):
        raise ApiError(f"поле {key} должно быть строкой")
    return value


def check_parameter(parameter):
    """Проверяет параметр задачи: битрейт MP3 вида 128k."""
    if parameter is not None and not BITRATE_PATTERN.fullmatch(parameter):
        raise ApiError("поле parameter должно быть битрейтом вида 128k")
    return parameter


def split_tags(tags):
    """Разбивает строку тегов, перечисленных через запятую."""
    parts = (tag.strip() for tag in (tags or "").split(TAG_SEPARATOR))
    return [tag for tag in parts if tag]


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


def identifier_filter(args):
    """Фильтр по полю identifier из строки запроса, если он задан."""
    if "identifier" not in args:
        return {}
    return {"identifier": parse_identifier(args["identifier"])}


class Service:
    """Операции над таблицами Entity, Query, Feedback и отчётом."""

    def __init__(self, storage, runner, clock):
        """Связывает сервис с хранилищем, исполнителем задач и часами."""
        self.storage = storage
        self.runner = runner
        self.clock = clock

    def save_entity(self, identifier, body):
        """Создаёт запись Entity."""
        record = {
            "identifier": parse_identifier(identifier),
            "datetime": timestamp(self.clock),
            **{key: optional_text(body, key) for key in ENTITY_FIELDS},
        }
        if not self.storage.insert(ENTITY, record):
            raise ApiError(f"Entity {identifier} уже существует")
        return record

    def delete_entity(self, body):
        """Удаляет Entity вместе с её запросами и их результатами."""
        identifier = require_identifier(body, "identifier")
        if not self.storage.delete(ENTITY, identifier):
            raise ApiError(f"Entity {identifier} не найдена")
        for query in self.storage.select(QUERY, {"entity": identifier}):
            self._drop_query(query["identifier"])
        return {"identifier": identifier}

    def show_entity(self, args):
        """Ищет записи Entity по полям identifier, ip, locale, platform."""
        filters = {**identifier_filter(args), **pick(args, ENTITY_FIELDS)}
        return self.storage.select(ENTITY, filters)

    def renew_entity(self, args):
        """Изменяет поля ip, locale и platform записи Entity."""
        identifier = parse_identifier(require_text(args, "identifier"))
        return self._update(ENTITY, identifier, pick(args, ENTITY_FIELDS))

    def save_query(self, identifier, body):
        """Создаёт запрос Query и запускает задачу извлечения звука."""
        record = {
            "identifier": parse_identifier(identifier),
            "datetime": timestamp(self.clock),
            "parameter": check_parameter(optional_text(body, "parameter")),
            "entity": require_identifier(body, "entity"),
            "description": optional_text(body, "description"),
            "tags": optional_text(body, "tags"),
            "status": STATUS_PENDING,
        }
        data = decode_source(body)
        if not self.storage.select(ENTITY, {"identifier": record["entity"]}):
            raise ApiError(f"Entity {record['entity']} не найдена")
        if not self.storage.insert(QUERY, record):
            raise ApiError(f"Query {identifier} уже существует")
        self.runner.submit(record["identifier"], data, record["parameter"])
        return record

    def delete_query(self, body):
        """Удаляет запрос Query вместе с его результатами."""
        identifier = require_identifier(body, "identifier")
        if not self._drop_query(identifier):
            raise ApiError(f"Query {identifier} не найден")
        return {"identifier": identifier}

    def show_query(self, entity, args):
        """Ищет запросы Entity по полям identifier, status и тегу tag."""
        filters = {
            "entity": parse_identifier(entity, "entity"),
            **identifier_filter(args),
            **pick(args, ("status",)),
        }
        queries = self.storage.select(QUERY, filters)
        if "tag" in args:
            queries = [
                query for query in queries
                if args["tag"] in split_tags(query["tags"])
            ]
        return queries

    def renew_query(self, args):
        """Изменяет описание и теги запроса Query."""
        identifier = parse_identifier(require_text(args, "identifier"))
        changes = pick(args, ("description", "tags"))
        return self._update(QUERY, identifier, changes)

    def show_feedback(self, query, args):
        """Ищет результаты запроса Query по полям identifier и status."""
        filters = {
            "query": parse_identifier(query, "query"),
            **identifier_filter(args),
            **pick(args, ("status",)),
        }
        return self.storage.select(FEEDBACK, filters)

    def show_report(self):
        """Строит отчёт по формуле (11)."""
        queries = self.storage.select(QUERY, {})
        feedback = self.storage.select(FEEDBACK, {})
        return build_report(queries, feedback, timestamp(self.clock))

    def _update(self, table, identifier, changes):
        """Изменяет запись или возбуждает ApiError, если её нет."""
        record = self.storage.update(table, identifier, changes)
        if record is None:
            raise ApiError(f"запись {identifier} не найдена")
        return record

    def _drop_query(self, identifier):
        """Удаляет запрос и его результаты; True, если запрос был."""
        for item in self.storage.select(FEEDBACK, {"query": identifier}):
            self.storage.delete(FEEDBACK, item["identifier"])
        return self.storage.delete(QUERY, identifier)
