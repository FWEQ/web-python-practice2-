@echo off
setlocal
set TARGET=%1
if "%TARGET%"=="" set TARGET=help

if "%TARGET%"=="install" goto install
if "%TARGET%"=="samples" goto samples
if "%TARGET%"=="demo" goto demo
if "%TARGET%"=="test" goto test
if "%TARGET%"=="lint" goto lint
goto help

:install
uv sync
goto end

:samples
uv run python examples\make_samples.py samples
goto end

:demo
call :samples
if not exist samples\mp3 mkdir samples\mp3
for %%f in (samples\*.webm) do (
    echo %%f -^> samples\mp3\%%~nf.mp3
    uv run webm2mp3 < "%%f" > "samples\mp3\%%~nf.mp3"
)
goto end

:test
uv run pytest
goto end

:lint
uv run ruff check .
goto end

:help
echo Usage: run.bat [install^|samples^|demo^|test^|lint]

:end
endlocal
