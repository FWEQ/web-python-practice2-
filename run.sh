#!/usr/bin/env sh
set -e

target="${1:-help}"

case "$target" in
    install)
        uv sync
        ;;
    samples)
        uv run python examples/make_samples.py samples
        ;;
    demo)
        uv run python examples/make_samples.py samples
        mkdir -p samples/mp3
        for file in samples/*.webm; do
            name="$(basename "$file" .webm)"
            echo "$file -> samples/mp3/$name.mp3"
            uv run webm2mp3 < "$file" > "samples/mp3/$name.mp3"
        done
        ;;
    test)
        uv run pytest
        ;;
    lint)
        uv run ruff check .
        ;;
    *)
        echo "Usage: ./run.sh [install|samples|demo|test|lint]"
        ;;
esac
