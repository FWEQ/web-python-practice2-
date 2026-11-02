"""Веб-приложение Flask с HTTP API (таблица 11 варианта).

Все обработчики возвращают JSON вида {"ok": true, "result": ...}
либо {"ok": false, "error": "..."}. Доступ защищён базовой
аутентификацией по RFC 7617; без неё возвращается 401 Unauthorized.
"""

import hmac
from http import HTTPStatus

from flask import Flask, jsonify, request
from werkzeug.exceptions import HTTPException

from webm2mp3.service import ApiError

PREFIX = "/core/api/stable"
REALM = 'Basic realm="webm2mp3", charset="UTF-8"'


def ok(result):
    """Успешный ответ HTTP API."""
    return jsonify(ok=True, result=result)


def json_body():
    """Возвращает тело запроса, если это JSON-объект."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError("тело запроса должно быть JSON-объектом")
    return body


def same_secret(actual, expected):
    """Сравнивает строки за время, не зависящее от их содержимого."""
    return hmac.compare_digest(actual.encode(), expected.encode())


def is_authorized(auth, username, password):
    """Проверяет учётные данные базовой аутентификации."""
    return (
        auth is not None and auth.type == "basic"
        and same_secret(auth.username, username)
        and same_secret(auth.password, password)
    )


def register_auth(app, username, password):
    """Подключает проверку авторизации ко всем запросам."""

    @app.before_request
    def check_credentials():
        if is_authorized(request.authorization, username, password):
            return None
        response = jsonify(ok=False, error="требуется авторизация")
        response.status_code = HTTPStatus.UNAUTHORIZED
        response.headers["WWW-Authenticate"] = REALM
        return response


def register_errors(app):
    """Преобразует ошибки в ответы формата JSON."""

    @app.errorhandler(ApiError)
    def api_error(error):
        return jsonify(ok=False, error=str(error))

    @app.errorhandler(HTTPException)
    def http_error(error):
        response = jsonify(ok=False, error=error.description)
        response.status_code = error.code
        return response


def register_entity_routes(app, service):
    """Обработчики таблицы Entity (методы 1.1-1.4)."""

    @app.put(f"{PREFIX}/entity-save/<identifier>")
    def entity_save(identifier):
        return ok(service.save_entity(identifier, json_body()))

    @app.post(f"{PREFIX}/entity-delete")
    def entity_delete():
        return ok(service.delete_entity(json_body()))

    @app.get(f"{PREFIX}/entity-show")
    def entity_show():
        return ok(service.show_entity(request.args))

    @app.post(f"{PREFIX}/entity-renew")
    def entity_renew():
        return ok(service.renew_entity(request.args))


def register_query_routes(app, service):
    """Обработчики таблицы Query (методы 2.1-2.4)."""

    @app.put(f"{PREFIX}/query-save/<identifier>")
    def query_save(identifier):
        return ok(service.save_query(identifier, json_body()))

    @app.post(f"{PREFIX}/query-delete")
    def query_delete():
        return ok(service.delete_query(json_body()))

    @app.get(f"{PREFIX}/query-show/<entity>")
    def query_show(entity):
        return ok(service.show_query(entity, request.args))

    @app.post(f"{PREFIX}/query-renew")
    def query_renew():
        return ok(service.renew_query(request.args))


def register_report_routes(app, service):
    """Обработчики таблиц Feedback и Report (методы 3.1 и 4.1)."""

    @app.get(f"{PREFIX}/feedback-show/<query>")
    def feedback_show(query):
        return ok(service.show_feedback(query, request.args))

    @app.get(f"{PREFIX}/report-show")
    def report_show():
        return ok(service.show_report())


def create_app(service, username, password):
    """Создаёт приложение Flask поверх сервиса прикладной логики."""
    app = Flask(__name__)
    app.json.ensure_ascii = False
    register_auth(app, username, password)
    register_errors(app)
    register_entity_routes(app, service)
    register_query_routes(app, service)
    register_report_routes(app, service)
    return app
