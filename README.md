# webm2mp3

Веб-приложение с HTTP API для асинхронного извлечения звука в формате MP3
из файлов в формате WebM (практическая работа №2, вариант 11).

Проект состоит из двух частей:

- утилиты командной строки `webm2mp3`: WebM на стандартном вводе,
  MP3 на стандартном выводе;
- веб-приложения на Flask: принимает WebM через HTTP API, запускает
  утилиту в фоне через `subprocess` и хранит записи Entity, Query
  и Feedback.

## Структура

| Путь | Назначение |
|---|---|
| `src/webm2mp3/cli.py` | утилита командной строки (этап 1) |
| `src/webm2mp3/app.py` | маршруты Flask, авторизация, ответы JSON |
| `src/webm2mp3/service.py` | прикладная логика и проверка входных данных |
| `src/webm2mp3/storage.py` | слой доступа к данным в памяти |
| `src/webm2mp3/report.py` | отчёт по формуле (11) |
| `src/webm2mp3/tasks.py` | асинхронное выполнение задач в пуле потоков |
| `src/webm2mp3/server.py` | запуск сервера из командной строки |
| `src/webm2mp3/client.py` | клиент к HTTP API |
| `examples/` | генератор примеров WebM и демонстрационный клиент |
| `tests/` | тесты, в том числе модельные тесты hypothesis |

## Сборка и запуск

Требуется [uv](https://docs.astral.sh/uv/) и Python 3.12.

| Команда (Windows / Linux) | Действие |
|---|---|
| `run.bat install` / `./run.sh install` | установить зависимости |
| `run.bat samples` / `./run.sh samples` | сгенерировать 5 примеров WebM в `samples/` |
| `run.bat demo` / `./run.sh demo` | преобразовать примеры утилитой в `samples/mp3/` |
| `run.bat serve USER PASS` / `./run.sh serve USER PASS` | запустить сервер на `127.0.0.1:8080` |
| `run.bat client USER PASS` / `./run.sh client USER PASS` | отправить примеры на запущенный сервер |
| `run.bat test` / `./run.sh test` | запустить все тесты |
| `run.bat coverage` / `./run.sh coverage` | отчёт о покрытии ветвей модельными тестами |
| `run.bat lint` / `./run.sh lint` | проверить код линтером ruff |

## Этап 1. Утилита командной строки

Утилита читает содержимое файла WebM из стандартного ввода и
направляет звук MP3 в стандартный вывод. Видеодорожки отбрасываются,
первая звуковая дорожка кодируется кодеком `libmp3lame`.

`ffmpeg` ищется в следующем порядке:

1. путь из переменной окружения `FFMPEG_BINARY`;
2. `ffmpeg` из `PATH`;
3. бинарный файл из пакета `imageio-ffmpeg` (ставится автоматически).

| Параметр | Описание | По умолчанию |
|---|---|---|
| `-b`, `--bitrate` | битрейт MP3 | `192k` |

| Код завершения | Значение |
|---|---|
| `0` | звук успешно извлечён |
| `1` | ошибка ffmpeg: вход не WebM, нет звуковой дорожки и т. п. |
| `3` | пустой входной поток |

```sh
uv run webm2mp3 < video.webm > audio.mp3
uv run webm2mp3 --bitrate 128k < video.webm > audio.mp3
```

В PowerShell перенаправление `<` не поддерживается, используйте `cmd`:

```bat
cmd /c "uv run webm2mp3 < video.webm > audio.mp3"
```

Примеры входных данных (генерируются `examples/make_samples.py`):

| Файл | Содержимое |
|---|---|
| `01_sine_opus_mono.webm` | синус 440 Гц, 3 с, Opus, моно |
| `02_sine_vorbis_stereo.webm` | синус 1000 Гц, 5 с, Vorbis, стерео |
| `03_noise_opus.webm` | розовый шум, 2 с, Opus |
| `04_chord_opus_48k.webm` | аккорд до-мажор, 4 с, Opus, 48 кГц |
| `05_video_with_audio.webm` | видео VP8 и синус 440 Гц, Opus |

## Этап 2. HTTP API

### Запуск сервера

```sh
uv run webm2mp3-server --username admin --password secret
```

| Параметр | Описание | По умолчанию |
|---|---|---|
| `--username` | имя пользователя HTTP API (обязательный) | — |
| `--password` | пароль HTTP API (обязательный) | — |
| `--host` | адрес сервера | `127.0.0.1` |
| `--port` | порт сервера | `8080` |
| `--output-dir` | папка для полученных MP3 | `data/output` |
| `--workers` | число параллельно выполняемых задач | `2` |
| `--test-mode` | не запускать конвертацию, сразу завершать задачи | выключен |

### Авторизация

Все запросы требуют базовой аутентификации по RFC 7617
(`Authorization: Basic base64(user:password)`). Без неё или с неверными
данными сервер возвращает `401 Unauthorized` и заголовок
`WWW-Authenticate`. Иначе сервер всегда отвечает `200 OK` с телом JSON:

```json
{"ok": true, "result": "..."}
{"ok": false, "error": "описание ошибки"}
```

Несуществующие маршруты и методы дают `404` и `405` с телом того же вида.

### Данные

| Таблица | Поля |
|---|---|
| Entity | `identifier`, `name` |
| Query | `identifier`, `entity` → Entity, `datetime` (UTC, ISO 8601), `description`, `tags` (список строк) |
| Feedback | `query` → Query, `status` (`pending`, `running`, `done`, `failed`), `response` (путь к MP3 или текст ошибки) |

Идентификаторы состоят из латинских букв, цифр, `_` и `-` (до 64
символов). При удалении Entity удаляются её запросы, при удалении Query
удаляется его результат.

### Маршруты

Префикс всех маршрутов: `/core/api/stable`.

| № | Метод | Маршрут | Параметры | Действие |
|---|---|---|---|---|
| 1.1 | PUT | `/entity-save/:identifier` | тело `{"name"}` | создать Entity |
| 1.2 | POST | `/entity-delete` | тело `{"identifier"}` | удалить Entity |
| 1.3 | GET | `/entity-show` | `?identifier=&name=` | найти Entity |
| 1.4 | POST | `/entity-renew` | `?identifier=&name=` | изменить Entity |
| 2.1 | PUT | `/query-save/:identifier` | тело `{"entity", "source", "description", "tags"}` | создать Query и запустить задачу |
| 2.2 | POST | `/query-delete` | тело `{"identifier"}` | удалить Query |
| 2.3 | GET | `/query-show/:entity` | `?identifier=&tag=` | найти Query для Entity |
| 2.4 | POST | `/query-renew` | `?identifier=&description=&tags=a,b` | изменить Query |
| 3.1 | GET | `/feedback-show/:query` | `?status=` | найти результат Query |
| 4.1 | GET | `/report-show` | нет | отчёт по формуле (11) |

В методе 2.1 поле `source` содержит файл WebM в Base64. Сервер сразу
возвращает созданный Query, а Feedback со статусом `pending`
обрабатывается в фоне. Задача запускает `python -m webm2mp3.cli` через
`subprocess` и по завершении записывает в Feedback статус `done` и путь
к MP3 либо статус `failed` и текст ошибки. В тестовом режиме задача
сразу получает статус `done` и ответ `test-mode: N bytes`.

Отчёт 4.1 — полное внешнее соединение запросов Query, созданных менее
9 минут назад, с результатами Feedback по `Q.identifier = F.query` и
проекцией на поля `response`, `description` и `tags` (без повторов).
Для строки без пары отсутствующие поля равны `null`.

### Примеры

```sh
curl -u admin:secret -X PUT -H "Content-Type: application/json" \
     -d '{"name": "Иван"}' \
     http://127.0.0.1:8080/core/api/stable/entity-save/ivan

curl -u admin:secret -X PUT -H "Content-Type: application/json" \
     -d "{\"entity\": \"ivan\", \"tags\": [\"lecture\"], \"source\": \"$(base64 -w0 video.webm)\"}" \
     http://127.0.0.1:8080/core/api/stable/query-save/q1

curl -u admin:secret http://127.0.0.1:8080/core/api/stable/feedback-show/q1
curl -u admin:secret http://127.0.0.1:8080/core/api/stable/report-show
```

Через клиент на Python:

```python
from pathlib import Path
from webm2mp3.client import ApiClient

client = ApiClient("http://127.0.0.1:8080", "admin", "secret")
client.save_entity("ivan", "Иван")
client.save_query("q1", "ivan", Path("video.webm").read_bytes(),
                  description="лекция", tags=["lecture"])
print(client.show_feedback("q1").payload)
print(client.show_report().payload)
```

Методы `ApiClient` называются по схеме `действие_таблица`:
`save_entity`, `delete_entity`, `show_entity`, `renew_entity`,
`save_query`, `delete_query`, `show_query`, `renew_query`,
`show_feedback`, `show_report`. Каждый возвращает `Response(status,
payload)`.

## Тестирование

- `tests/test_api.py` — тестирование на основе модели. Автомат
  `RuleBasedStateMachine` из hypothesis выполняет случайные цепочки
  запросов через `ApiClient` к настоящему HTTP-серверу и сверяет ответы
  с моделью в памяти. Сервер работает в тестовом режиме с управляемыми
  часами, чтобы проверить окно отчёта в 9 минут. Автомат покрывает все
  обработчики: успешные операции, ошибки валидации, повторы,
  отсутствующие записи, 401, 404 и 405.
- `tests/test_cli.py` — утилита командной строки на примерах WebM.
- `tests/test_tasks.py` — реальное асинхронное выполнение задач.
- `tests/test_server.py` — разбор аргументов и авторизация сервера.

`run.bat coverage` запускает **только** модельные тесты под `coverage`
с учётом ветвей и выводит отчёт по модулям обработчиков HTTP API.
HTML-версия отчёта сохраняется в `htmlcov/`.
