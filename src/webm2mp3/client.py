"""Клиент к HTTP API веб-приложения webm2mp3.

Имена методов клиента имеют вид действие_таблица, например
save_entity соответствует маршруту entity-save.
"""

import base64
import json
import urllib.error
import urllib.parse
import urllib.request
from typing import NamedTuple

PREFIX = "/core/api/stable"
DEFAULT_TIMEOUT = 30


class Response(NamedTuple):
    """Ответ HTTP API: код состояния и разобранное тело JSON."""

    status: int
    payload: dict


def quote(value):
    """Экранирует значение для подстановки в путь маршрута."""
    return urllib.parse.quote(str(value), safe="")


def without_none(**fields):
    """Отбрасывает поля со значением None."""
    return {key: value for key, value in fields.items() if value is not None}


class ApiClient:
    """Клиент HTTP API с базовой аутентификацией по RFC 7617."""

    def __init__(self, base_url, username=None, password=None,
                 timeout=DEFAULT_TIMEOUT):
        """Создаёт клиент; без имени пользователя заголовок не шлётся."""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.headers = {"Accept": "application/json"}
        if username is not None:
            pair = "{}:{}".format(username, password or "").encode()
            token = base64.b64encode(pair).decode("ascii")
            self.headers["Authorization"] = f"Basic {token}"

    def request(self, method, route, params=None, body=None, data=None):
        """Выполняет запрос к маршруту HTTP API.

        Тело передаётся либо как объект body, сериализуемый в JSON,
        либо как готовые байты data.
        """
        url = f"{self.base_url}{PREFIX}/{route}"
        if params:
            url = f"{url}?{urllib.parse.urlencode(params)}"
        headers = dict(self.headers)
        if body is not None:
            data = json.dumps(body).encode()
        if data is not None:
            headers["Content-Type"] = "application/json"
        message = urllib.request.Request(url, data, headers, method=method)
        try:
            with urllib.request.urlopen(message, timeout=self.timeout) as r:
                return Response(r.status, json.load(r))
        except urllib.error.HTTPError as error:
            with error:
                return Response(error.code, json.load(error))

    def save_entity(self, identifier, ip=None, locale=None, platform=None):
        """1.1. Создаёт запись Entity."""
        body = without_none(ip=ip, locale=locale, platform=platform)
        route = f"entity-save/{quote(identifier)}"
        return self.request("PUT", route, body=body)

    def delete_entity(self, identifier):
        """1.2. Удаляет запись Entity."""
        body = {"identifier": identifier}
        return self.request("POST", "entity-delete", body=body)

    def show_entity(self, **filters):
        """1.3. Ищет Entity по полям identifier, ip, locale, platform."""
        return self.request("GET", "entity-show", params=filters)

    def renew_entity(self, identifier, **changes):
        """1.4. Изменяет поля ip, locale и platform записи Entity."""
        params = {"identifier": identifier, **changes}
        return self.request("POST", "entity-renew", params=params)

    def save_query(self, identifier, entity, source, parameter=None,
                   description=None, tags=None):
        """2.1. Создаёт запрос на извлечение звука из байтов WebM."""
        body = without_none(
            entity=entity, parameter=parameter, description=description,
            tags=tags, source=base64.b64encode(source).decode("ascii"),
        )
        route = f"query-save/{quote(identifier)}"
        return self.request("PUT", route, body=body)

    def delete_query(self, identifier):
        """2.2. Удаляет запрос Query."""
        body = {"identifier": identifier}
        return self.request("POST", "query-delete", body=body)

    def show_query(self, entity, **filters):
        """2.3. Ищет запросы Entity по полям identifier, status и tag."""
        route = f"query-show/{quote(entity)}"
        return self.request("GET", route, params=filters)

    def renew_query(self, identifier, description=None, tags=None):
        """2.4. Изменяет описание и теги запроса Query."""
        params = without_none(identifier=identifier,
                              description=description, tags=tags)
        return self.request("POST", "query-renew", params=params)

    def show_feedback(self, query, **filters):
        """3.1. Ищет результаты запроса Query по полям identifier, status."""
        route = f"feedback-show/{quote(query)}"
        return self.request("GET", route, params=filters)

    def show_report(self):
        """4.1. Возвращает отчёт по формуле (11)."""
        return self.request("GET", "report-show")
