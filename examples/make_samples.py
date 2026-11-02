"""Генерирует примеры входных файлов WebM для демонстрации утилиты.

Файлы создаются синтетически средствами ffmpeg, поэтому не хранятся
в репозитории. Использование: python examples/make_samples.py [папка]
"""

import subprocess
import sys
from pathlib import Path

from webm2mp3.cli import find_ffmpeg

DEFAULT_DIR = Path("samples")

SINE_440 = "sine=frequency=440:duration=3"
SINE_1000 = "sine=frequency=1000:duration=5"
NOISE = "anoisesrc=color=pink:duration=2:amplitude=0.3"
CHORD = (
    "aevalsrc=0.3*sin(2*PI*262*t)+0.3*sin(2*PI*330*t)"
    "+0.3*sin(2*PI*392*t):d=4"
)
VIDEO = "testsrc=size=320x240:rate=25:duration=3"

SAMPLES = {
    "01_sine_opus_mono.webm": [
        "-f", "lavfi", "-i", SINE_440, "-c:a", "libopus",
    ],
    "02_sine_vorbis_stereo.webm": [
        "-f", "lavfi", "-i", SINE_1000, "-ac", "2", "-c:a", "libvorbis",
    ],
    "03_noise_opus.webm": [
        "-f", "lavfi", "-i", NOISE, "-c:a", "libopus",
    ],
    "04_chord_opus_48k.webm": [
        "-f", "lavfi", "-i", CHORD, "-ar", "48000", "-c:a", "libopus",
    ],
    "05_video_with_audio.webm": [
        "-f", "lavfi", "-i", VIDEO, "-f", "lavfi", "-i", SINE_440,
        "-c:v", "libvpx", "-b:v", "200k", "-c:a", "libopus",
        "-shortest",
    ],
}


def make_samples(directory):
    """Создаёт все примеры в указанной папке и возвращает их пути."""
    directory.mkdir(parents=True, exist_ok=True)
    ffmpeg = find_ffmpeg()
    paths = []
    for name, arguments in SAMPLES.items():
        path = directory / name
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y"]
        subprocess.run([*command, *arguments, str(path)], check=True)
        paths.append(path)
    return paths


def main(argv=None):
    """Точка входа сценария генерации примеров."""
    argv = sys.argv[1:] if argv is None else argv
    directory = Path(argv[0]) if argv else DEFAULT_DIR
    for path in make_samples(directory):
        print(path)


if __name__ == "__main__":
    main()
