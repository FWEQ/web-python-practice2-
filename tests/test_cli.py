"""Тесты утилиты командной строки webm2mp3."""

import io
import subprocess
import sys

from webm2mp3 import cli

MP3_SIGNATURE = b"ID3"
LOW_BITRATE = "32k"
HIGH_BITRATE = "320k"


def run_main(data, argv=()):
    """Запускает утилиту в текущем процессе и возвращает результат."""
    stdout, stderr = io.BytesIO(), io.StringIO()
    code = cli.main(list(argv), io.BytesIO(data), stdout, stderr)
    return code, stdout.getvalue(), stderr.getvalue()


def test_all_samples_are_converted(samples):
    """Каждый пример WebM преобразуется в непустой MP3."""
    for path in samples:
        code, audio, errors = run_main(path.read_bytes())
        assert code == cli.EXIT_OK, errors
        assert audio.startswith(MP3_SIGNATURE)


def test_bitrate_changes_output_size(samples):
    """Меньший битрейт даёт меньший по размеру MP3."""
    data = samples[1].read_bytes()
    _, low, _ = run_main(data, ["--bitrate", LOW_BITRATE])
    _, high, _ = run_main(data, ["--bitrate", HIGH_BITRATE])
    assert len(low) < len(high)


def test_empty_input():
    """Пустой ввод завершает работу с отдельным кодом ошибки."""
    code, audio, errors = run_main(b"")
    assert code == cli.EXIT_EMPTY_INPUT
    assert not audio
    assert "пустой" in errors


def test_invalid_input():
    """Данные, не являющиеся WebM, приводят к ошибке конвертации."""
    code, audio, errors = run_main(b"not a webm file")
    assert code == cli.EXIT_CONVERSION_FAILED
    assert not audio
    assert errors


def test_video_without_audio(silent_video):
    """WebM без звуковой дорожки приводит к ошибке конвертации."""
    code, audio, _ = run_main(silent_video.read_bytes())
    assert code == cli.EXIT_CONVERSION_FAILED
    assert not audio


def test_missing_ffmpeg(monkeypatch):
    """Недоступный ffmpeg превращается в ошибку конвертации."""
    monkeypatch.setenv(cli.FFMPEG_ENV, "no-such-ffmpeg-binary")
    code, _, errors = run_main(b"data")
    assert code == cli.EXIT_CONVERSION_FAILED
    assert "ffmpeg" in errors


def test_ffmpeg_from_environment(monkeypatch):
    """Переменная окружения FFMPEG_BINARY имеет высший приоритет."""
    monkeypatch.setenv(cli.FFMPEG_ENV, "custom-ffmpeg")
    assert cli.find_ffmpeg() == "custom-ffmpeg"


def test_standard_streams(samples):
    """Утилита работает через стандартные потоки отдельного процесса."""
    result = subprocess.run(
        [sys.executable, "-m", "webm2mp3.cli"],
        input=samples[0].read_bytes(),
        capture_output=True,
        check=False,
    )
    assert result.returncode == cli.EXIT_OK
    assert result.stdout.startswith(MP3_SIGNATURE)
