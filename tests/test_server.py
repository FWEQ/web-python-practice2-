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


def test_build_app_uses_credentials(tmp_path):
    """Учётные данные из командной строки защищают HTTP API."""
    args = server.parse_args(
        [*CREDENTIALS, "--test-mode", "--output-dir", str(tmp_path)]
    )
    app, runner = server.build_app(args)
    client = app.test_client()
    url = "/core/api/stable/report-show"
    denied = client.get(url, headers=basic("user", "wrong"))
    allowed = client.get(url, headers=basic("user", "secret"))
    runner.shutdown()
    assert denied.status_code == HTTPStatus.UNAUTHORIZED
    assert "Basic" in denied.headers["WWW-Authenticate"]
    assert allowed.status_code == HTTPStatus.OK
    assert allowed.json == {"ok": True, "result": []}
