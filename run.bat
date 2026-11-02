@echo off
setlocal
set TARGET=%1
if "%TARGET%"=="" set TARGET=help

if "%TARGET%"=="install" goto install
if "%TARGET%"=="samples" goto samples
if "%TARGET%"=="demo" goto demo
if "%TARGET%"=="serve" goto serve
if "%TARGET%"=="client" goto client
if "%TARGET%"=="test" goto test
if "%TARGET%"=="coverage" goto coverage
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

:serve
if "%3"=="" goto help
uv run webm2mp3-server --username %2 --password %3 %4 %5 %6 %7 %8 %9
goto end

:client
if "%3"=="" goto help
call :samples
uv run python examples\client_demo.py http://127.0.0.1:8080 %2 %3 samples\01_sine_opus_mono.webm samples\05_video_with_audio.webm
goto end

:test
uv run pytest
goto end

:coverage
uv run coverage erase
uv run coverage run -m pytest tests\test_api.py
uv run coverage report -m --include=*/app.py,*/service.py,*/report.py,*/storage*.py,*/client.py
uv run coverage html --include=*/app.py,*/service.py,*/report.py,*/storage*.py,*/client.py
goto end

:lint
uv run ruff check .
goto end

:help
echo Usage: run.bat install^|samples^|demo^|test^|coverage^|lint
echo        run.bat serve USERNAME PASSWORD [server options]
echo        run.bat client USERNAME PASSWORD

:end
endlocal
