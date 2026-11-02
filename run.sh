#!/usr/bin/env sh
set -e

target="${1:-help}"
handlers="*/app.py,*/service.py,*/report.py,*/storage*.py,*/client.py"

usage() {
    echo "Usage: ./run.sh install|samples|demo|test|coverage|lint"
    echo "       ./run.sh serve USERNAME PASSWORD [server options]"
    echo "       ./run.sh client USERNAME PASSWORD"
}

samples() {
    uv run python examples/make_samples.py samples
}

case "$target" in
    install)
        uv sync
        ;;
    samples)
        samples
        ;;
    demo)
        samples
        mkdir -p samples/mp3
        for file in samples/*.webm; do
            name="$(basename "$file" .webm)"
            echo "$file -> samples/mp3/$name.mp3"
            uv run webm2mp3 < "$file" > "samples/mp3/$name.mp3"
        done
        ;;
    serve)
        [ "$#" -ge 3 ] || { usage; exit 1; }
        username="$2"
        password="$3"
        shift 3
        uv run webm2mp3-server --username "$username" \
            --password "$password" "$@"
        ;;
    client)
        [ "$#" -ge 3 ] || { usage; exit 1; }
        samples
        uv run python examples/client_demo.py http://127.0.0.1:8080 \
            "$2" "$3" samples/01_sine_opus_mono.webm \
            samples/05_video_with_audio.webm
        ;;
    test)
        uv run pytest
        ;;
    coverage)
        uv run coverage erase
        uv run coverage run -m pytest tests/test_api.py
        uv run coverage report -m --include="$handlers"
        uv run coverage html --include="$handlers"
        ;;
    lint)
        uv run ruff check .
        ;;
    *)
        usage
        ;;
esac
