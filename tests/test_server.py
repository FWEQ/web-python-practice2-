"""Тесты запуска веб-приложения из командной строки."""

import base64
from http import HTTPStatus

import pytest

from webm2mp3 import server

CREDENTIALS = ["--username", "user", "--password", "secret"]


def basic(username, password):
    """Заголовок базовой аутентификации."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def test_credentials_are_required():
    """Без имени пользователя и пароля сервер не запускается."""
    with pytest.raises(SystemExit):
        server.parse_args([])


def build(tmp_path, *options):
    """Собирает приложение с учётными данными и тестовым режимом."""
    args = server.parse_args([
        *CREDENTIALS, "--test-mode", "--output-dir", str(tmp_path),
        "--database", str(tmp_path / "db.json"), *options,
    ])
    return server.build_app(args)


def test_build_app_uses_credentials(tmp_path):
    """Учётные данные из командной строки защищают HTTP API."""
    app, runner, storage = build(tmp_path, "--storage", "memory")
    client = app.test_client()
    url = "/core/api/stable/report-show"
    denied = client.get(url, headers=basic("user", "wrong"))
    allowed = client.get(url, headers=basic("user", "secret"))
    runner.shutdown()
    storage.close()
    assert denied.status_code == HTTPStatus.UNAUTHORIZED
    assert "Basic" in denied.headers["WWW-Authenticate"]
    assert allowed.status_code == HTTPStatus.OK
    assert allowed.json == {"ok": True, "result": []}


def test_tinydb_storage_persists(tmp_path):
    """По умолчанию данные сохраняются в файл TinyDB между запусками."""
    url = "/core/api/stable/entity-save/1"
    headers = basic("user", "secret")
    app, runner, storage = build(tmp_path)
    saved = app.test_client().put(url, json={"locale": "ru_RU"},
                                  headers=headers)
    storage.close()
    app, runner, storage = build(tmp_path)
    found = app.test_client().get(
        "/core/api/stable/entity-show", headers=headers
    )
    storage.close()
    assert found.json["result"] == [saved.json["result"]]
    assert found.json["result"][0]["locale"] == "ru_RU"
