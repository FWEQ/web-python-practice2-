"""Общие фикстуры тестов."""

import subprocess

import pytest
from make_samples import make_samples

from webm2mp3.cli import find_ffmpeg


@pytest.fixture(scope="session")
def samples(tmp_path_factory):
    """Пути к сгенерированным примерам WebM со звуком."""
    return make_samples(tmp_path_factory.mktemp("samples"))


@pytest.fixture(scope="session")
def silent_video(tmp_path_factory):
    """Путь к файлу WebM, содержащему только видеодорожку."""
    path = tmp_path_factory.mktemp("video") / "video_only.webm"
    subprocess.run(
        [
            find_ffmpeg(), "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc=size=64x64:rate=5:duration=1",
            "-c:v", "libvpx", str(path),
        ],
        check=True,
    )
    return path
