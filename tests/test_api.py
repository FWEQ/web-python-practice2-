"""Тестирование HTTP API на основе модели средствами hypothesis.

Конечный автомат RuleBasedStateMachine выполняет случайные цепочки
запросов через ApiClient к настоящему HTTP-серверу и сверяет ответы
с простой моделью таблиц Entity, Query и Feedback в памяти.
"""

import itertools
import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus

import pytest
from hypothesis import HealthCheck, settings
from hypothesis import strategies as st
from hypothesis.stateful import (
    Bundle,
    RuleBasedStateMachine,
    rule,
    run_state_machine_as_test,
)
from werkzeug.serving import make_server

from webm2mp3.app import create_app
from webm2mp3.client import ApiClient
from webm2mp3.service import Service
from webm2mp3.storage import MemoryStorage
from webm2mp3.storage_tinydb import TinyDBStorage
from webm2mp3.tasks import STATUS_DONE, TaskRunner, stub_response

USERNAME = "admin"
PASSWORD = "пароль"
HOST = "127.0.0.1"
POLL_INTERVAL = 0.01
REPORT_MINUTES = 9
START = datetime(2026, 11, 3, tzinfo=timezone.utc)

IDS = st.text(alphabet="abc", min_size=1, max_size=2)
BAD_IDS = st.sampled_from(["bad!id", "a b", "x" * 65, "точка"])
NAMES = st.text(alphabet="абвxyz ", min_size=1, max_size=6)
DESCRIPTIONS = st.text(alphabet="абв de", max_size=6)
TAG = st.text(alphabet="xyz", min_size=1, max_size=2)
TAGS = st.lists(TAG, max_size=3)
SOURCES = st.binary(min_size=1, max_size=16)
STATUSES = st.sampled_from(["pending", "running", "done", "failed"])
MINUTES = st.integers(min_value=0, max_value=REPORT_MINUTES + 3)

VALID_QUERY = {"entity": "a", "description": "", "tags": [], "source": "AA=="}
INVALID_QUERY_BODIES = [
    {"description": "", "tags": [], "source": "AA=="},
    {**VALID_QUERY, "entity": 5},
    {**VALID_QUERY, "description": 5},
    {**VALID_QUERY, "tags": "x"},
    {**VALID_QUERY, "tags": [5]},
    {**VALID_QUERY, "tags": [""]},
    {**VALID_QUERY, "tags": ["a,b"]},
    {**VALID_QUERY, "source": "@@@"},
    {**VALID_QUERY, "source": ""},
    {"entity": "a"},
]
BODY_ENDPOINTS = [
    ("PUT", "entity-save/a"),
    ("POST", "entity-delete"),
    ("PUT", "query-save/a"),
    ("POST", "query-delete"),
]
MALFORMED_BODIES = [b"", b"{", b"[]", b'"text"']
INVALID_ENTITY_REQUESTS = st.sampled_from([
    *[("PUT", "entity-save/a", {"body": body})
      for body in ({}, {"name": 5}, {"name": ""})],
    *[("POST", "entity-delete", {"body": body})
      for body in ({}, {"identifier": 5})],
    *[("POST", "entity-renew", {"params": params})
      for params in ({}, {"identifier": "a"}, {"name": "x"})],
    *[(method, route, {"data": data})
      for method, route in BODY_ENDPOINTS for data in MALFORMED_BODIES],
])
INVALID_QUERY_REQUESTS = st.sampled_from([
    *[("PUT", "query-save/a", {"body": body})
      for body in INVALID_QUERY_BODIES],
    *[("POST", "query-delete", {"body": body})
      for body in ({}, {"identifier": 5})],
    *[("POST", "query-renew", {"params": params})
      for params in ({}, {"description": "x"})],
])
WRONG_ROUTES = st.sampled_from([
    ("GET", "unknown", HTTPStatus.NOT_FOUND),
    ("GET", "entity-save", HTTPStatus.NOT_FOUND),
    ("GET", "entity-delete", HTTPStatus.METHOD_NOT_ALLOWED),
    ("DELETE", "report-show", HTTPStatus.METHOD_NOT_ALLOWED),
])

SETTINGS = settings(
    max_examples=100,
    stateful_step_count=40,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


class FakeClock:
    """Управляемые часы для проверки временного окна отчёта."""

    def __init__(self):
        """Устанавливает начальный момент времени."""
        self.now = START

    def __call__(self):
        """Возвращает текущий момент времени."""
        return self.now


class Dispatcher:
    """WSGI-приложение, перенаправляющее запросы текущему app."""

    def __init__(self):
        """Создаёт диспетчер без приложения."""
        self.app = None

    def __call__(self, environ, start_response):
        """Передаёт запрос текущему приложению."""
        return self.app(environ, start_response)


def without_none(**fields):
    """Отбрасывает поля со значением None."""
    return {key: value for key, value in fields.items() if value is not None}


def fits(record, filters):
    """Проверяет, что запись удовлетворяет фильтру модели."""
    return all(record[key] == value for key, value in filters.items())


def canonical(rows):
    """Приводит список записей к сравнимому виду без учёта порядка."""
    return sorted(
        {json.dumps(row, sort_keys=True, ensure_ascii=False) for row in rows}
    )


class ApiMachine(RuleBasedStateMachine):
    """Модель HTTP API: сверяет ответы сервера с ожидаемыми."""

    entity_ids = Bundle("entity_ids")
    query_ids = Bundle("query_ids")
    dispatcher = None
    base_url = None
    storage_factory = None

    def __init__(self):
        """Поднимает чистое приложение и пустую модель."""
        super().__init__()
        self.clock = FakeClock()
        self.storage = self.storage_factory()
        runner = TaskRunner(self.storage, "unused", test_mode=True)
        service = Service(self.storage, runner, self.clock)
        self.dispatcher.app = create_app(service, USERNAME, PASSWORD)
        self.client = ApiClient(self.base_url, USERNAME, PASSWORD)
        self.entities = {}
        self.queries = {}
        self.feedback = {}

    def teardown(self):
        """Закрывает хранилище после прогона."""
        self.storage.close()

    def expect(self, response, success):
        """Проверяет код 200 и флаг ok; возвращает поле result."""
        assert response.status == HTTPStatus.OK
        assert response.payload["ok"] is success, response.payload
        return response.payload.get("result")

    def forget_query(self, identifier):
        """Удаляет запрос и его результат из модели."""
        del self.queries[identifier]
        del self.feedback[identifier]

    def expected_report(self):
        """Отчёт по формуле (11), вычисленный по модели."""
        threshold = self.clock() - timedelta(minutes=REPORT_MINUTES)
        recent = {
            key: query for key, query in self.queries.items()
            if datetime.fromisoformat(query["datetime"]) > threshold
        }
        rows = [
            {"response": self.feedback[key]["response"],
             "description": query["description"], "tags": query["tags"]}
            for key, query in recent.items()
        ]
        rows += [
            {"response": item["response"], "description": None,
             "tags": None}
            for key, item in self.feedback.items() if key not in recent
        ]
        return canonical(rows)

    @rule(target=entity_ids, identifier=IDS, name=NAMES)
    def save_entity(self, identifier, name):
        """1.1: создание Entity."""
        success = identifier not in self.entities
        response = self.client.save_entity(identifier, name)
        result = self.expect(response, success)
        if success:
            self.entities[identifier] = {"identifier": identifier,
                                         "name": name}
            assert result == self.entities[identifier]
        return identifier

    @rule(identifier=entity_ids)
    def delete_entity(self, identifier):
        """1.2: удаление Entity вместе с запросами."""
        success = identifier in self.entities
        self.expect(self.client.delete_entity(identifier), success)
        if success:
            del self.entities[identifier]
            owned = [key for key, query in self.queries.items()
                     if query["entity"] == identifier]
            for key in owned:
                self.forget_query(key)

    @rule(identifier=st.none() | IDS, name=st.none() | NAMES)
    def show_entity(self, identifier, name):
        """1.3: поиск Entity."""
        filters = without_none(identifier=identifier, name=name)
        result = self.expect(self.client.show_entity(**filters), True)
        expected = [e for e in self.entities.values() if fits(e, filters)]
        assert canonical(result) == canonical(expected)

    @rule(identifier=entity_ids, name=NAMES)
    def renew_entity(self, identifier, name):
        """1.4: изменение Entity."""
        success = identifier in self.entities
        response = self.client.renew_entity(identifier, name)
        result = self.expect(response, success)
        if success:
            self.entities[identifier]["name"] = name
            assert result == self.entities[identifier]

    @rule(target=query_ids, identifier=IDS, entity=entity_ids,
          source=SOURCES,
          description=DESCRIPTIONS, tags=TAGS)
    def save_query(self, identifier, entity, source, description, tags):
        """2.1: создание Query и запуск задачи в тестовом режиме."""
        success = entity in self.entities and identifier not in self.queries
        response = self.client.save_query(identifier, entity, source,
                                          description, tags)
        result = self.expect(response, success)
        if success:
            self.queries[identifier] = {
                "identifier": identifier, "entity": entity,
                "datetime": self.clock().isoformat(),
                "description": description, "tags": tags,
            }
            self.feedback[identifier] = {
                "query": identifier, "status": STATUS_DONE,
                "response": stub_response(source),
            }
            assert result == self.queries[identifier]
        return identifier

    @rule(identifier=query_ids, entity=entity_ids, source=SOURCES)
    def save_duplicate_query(self, identifier, entity, source):
        """2.1: повторное создание Query с занятым идентификатором."""
        self.save_query(identifier, entity, source, "", [])

    @rule(identifier=query_ids)
    def delete_query(self, identifier):
        """2.2: удаление Query."""
        success = identifier in self.queries
        self.expect(self.client.delete_query(identifier), success)
        if success:
            self.forget_query(identifier)

    @rule(entity=entity_ids, identifier=st.none() | IDS,
          tag=st.none() | TAG)
    def show_query(self, entity, identifier, tag):
        """2.3: поиск Query по Entity."""
        filters = without_none(identifier=identifier, tag=tag)
        result = self.expect(self.client.show_query(entity, **filters), True)
        expected = [
            query for query in self.queries.values()
            if query["entity"] == entity
            and identifier in (None, query["identifier"])
            and (tag is None or tag in query["tags"])
        ]
        assert canonical(result) == canonical(expected)

    @rule(identifier=query_ids, description=st.none() | DESCRIPTIONS,
          tags=st.none() | TAGS)
    def renew_query(self, identifier, description, tags):
        """2.4: изменение Query."""
        success = identifier in self.queries
        response = self.client.renew_query(identifier, description, tags)
        result = self.expect(response, success)
        if success:
            changes = without_none(description=description, tags=tags)
            self.queries[identifier].update(changes)
            assert result == self.queries[identifier]

    @rule(query=query_ids, status=st.none() | STATUSES)
    def show_feedback(self, query, status):
        """3.1: поиск Feedback по Query."""
        filters = without_none(status=status)
        result = self.expect(self.client.show_feedback(query, **filters),
                             True)
        expected = [
            item for key, item in self.feedback.items()
            if key == query and fits(item, filters)
        ]
        assert canonical(result) == canonical(expected)

    @rule()
    def show_report(self):
        """4.1: отчёт по формуле (11)."""
        result = self.expect(self.client.show_report(), True)
        assert len(result) == len(canonical(result))
        assert canonical(result) == self.expected_report()

    @rule(minutes=MINUTES)
    def advance_time(self, minutes):
        """Сдвигает часы сервера и модели."""
        self.clock.now += timedelta(minutes=minutes)

    @rule(password=st.sampled_from([None, "", "wrong"]))
    def unauthorized(self, password):
        """Запрос без авторизации или с неверным паролем."""
        username = None if password is None else USERNAME
        client = ApiClient(self.base_url, username, password)
        response = client.show_report()
        assert response.status == HTTPStatus.UNAUTHORIZED
        assert response.payload["ok"] is False

    @rule(wrong=WRONG_ROUTES)
    def wrong_route(self, wrong):
        """Несуществующий маршрут или неподдерживаемый метод."""
        method, route, status = wrong
        response = self.client.request(method, route)
        assert response.status == status
        assert response.payload["ok"] is False

    @rule(identifier=BAD_IDS, name=NAMES, source=SOURCES)
    def bad_identifier(self, identifier, name, source):
        """Создание записей с недопустимым идентификатором."""
        self.expect(self.client.save_entity(identifier, name), False)
        self.expect(self.client.save_query(identifier, "a", source), False)

    @rule(request=INVALID_ENTITY_REQUESTS | INVALID_QUERY_REQUESTS)
    def invalid_request(self, request):
        """Запрос с некорректным телом или без обязательных полей."""
        method, route, options = request
        self.expect(self.client.request(method, route, **options), False)

    @rule(request=INVALID_QUERY_REQUESTS)
    def invalid_query_request(self, request):
        """Запрос к таблице Query с некорректными данными."""
        self.invalid_request(request)


@pytest.fixture(scope="module")
def server():
    """HTTP-сервер werkzeug в отдельном потоке."""
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    dispatcher = Dispatcher()
    http = make_server(HOST, 0, dispatcher, threaded=True)
    thread = threading.Thread(
        target=http.serve_forever,
        kwargs={"poll_interval": POLL_INTERVAL},
        daemon=True,
    )
    thread.start()
    yield dispatcher, f"http://{HOST}:{http.server_port}"
    http.shutdown()
    thread.join()


def run_machine(server, storage_factory):
    """Запускает модельное тестирование с заданным хранилищем."""
    dispatcher, base_url = server
    machine = type("Machine", (ApiMachine,), {
        "dispatcher": dispatcher,
        "base_url": base_url,
        "storage_factory": staticmethod(storage_factory),
    })
    run_state_machine_as_test(machine, settings=SETTINGS)


def test_api_with_memory_storage(server):
    """Модельное тестирование HTTP API с хранилищем в памяти."""
    run_machine(server, MemoryStorage)


def test_api_with_tinydb_storage(server, tmp_path):
    """Модельное тестирование HTTP API со слоем доступа на TinyDB."""
    files = itertools.count()

    def make_storage():
        return TinyDBStorage(tmp_path / f"db{next(files)}.json")

    run_machine(server, make_storage)
