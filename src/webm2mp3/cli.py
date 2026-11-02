"""Утилита командной строки для извлечения звука MP3 из WebM.

Утилита читает содержимое файла WebM из стандартного ввода и
направляет полученный звук в формате MP3 в стандартный вывод.
Сообщения об ошибках выводятся в стандартный поток ошибок.
"""

import argparse
import os
import shutil
import subprocess
import sys

import imageio_ffmpeg

EXIT_OK = 0
EXIT_CONVERSION_FAILED = 1
EXIT_EMPTY_INPUT = 3
DEFAULT_BITRATE = "192k"
FFMPEG_ENV = "FFMPEG_BINARY"


class ConversionError(Exception):
    """Ошибка извлечения звука средствами ffmpeg."""


def find_ffmpeg():
    """Возвращает путь к исполняемому файлу ffmpeg.

    Порядок поиска: переменная окружения FFMPEG_BINARY, ffmpeg из
    PATH, бинарный файл из пакета imageio-ffmpeg.
    """
    configured = os.environ.get(FFMPEG_ENV)
    if configured:
        return configured
    return shutil.which("ffmpeg") or imageio_ffmpeg.get_ffmpeg_exe()


def build_command(ffmpeg, bitrate):
    """Формирует аргументы ffmpeg для работы через каналы ввода-вывода.

    Видеодорожки отбрасываются, первая звуковая дорожка кодируется
    кодеком libmp3lame с указанным битрейтом.
    """
    return [
        ffmpeg, "-hide_banner", "-loglevel", "error",
        "-f", "matroska", "-i", "pipe:0",
        "-vn", "-map", "0:a:0",
        "-codec:a", "libmp3lame", "-b:a", bitrate,
        "-f", "mp3", "pipe:1",
    ]


def convert(data, bitrate=DEFAULT_BITRATE):
    """Извлекает звук MP3 из байтов WebM и возвращает байты MP3.

    Возбуждает ConversionError, если ffmpeg не удалось запустить
    или он завершился с ошибкой.
    """
    command = build_command(find_ffmpeg(), bitrate)
    try:
        result = subprocess.run(
            command, input=data, capture_output=True, check=False
        )
    except OSError as error:
        message = f"не удалось запустить ffmpeg: {error}"
        raise ConversionError(message) from error
    if result.returncode != EXIT_OK:
        message = result.stderr.decode("utf-8", errors="replace")
        raise ConversionError(message.strip() or "ошибка ffmpeg")
    return result.stdout


def parse_args(argv):
    """Разбирает аргументы командной строки."""
    parser = argparse.ArgumentParser(
        prog="webm2mp3",
        description=(
            "Читает WebM из стандартного ввода и пишет MP3 "
            "в стандартный вывод."
        ),
    )
    parser.add_argument(
        "-b", "--bitrate", default=DEFAULT_BITRATE,
        help="битрейт MP3, например 128k (по умолчанию %(default)s)",
    )
    return parser.parse_args(argv)


def main(argv=None, stdin=None, stdout=None, stderr=None):
    """Точка входа утилиты; возвращает код завершения процесса."""
    args = parse_args(argv)
    stdin = stdin or sys.stdin.buffer
    stdout = stdout or sys.stdout.buffer
    stderr = stderr or sys.stderr
    data = stdin.read()
    if not data:
        print("webm2mp3: пустой входной поток", file=stderr)
        return EXIT_EMPTY_INPUT
    try:
        audio = convert(data, args.bitrate)
    except ConversionError as error:
        print(f"webm2mp3: {error}", file=stderr)
        return EXIT_CONVERSION_FAILED
    stdout.write(audio)
    stdout.flush()
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
