@echo off
echo ========================================
echo M3U IPTV Stream Checker
echo ========================================
echo.

REM Wechsle ins Skript-Verzeichnis
cd /d "%~dp0"

REM Aktiviere Virtual Environment
call C:\iptv-main\m3u\venv\Scripts\activate.bat

REM ========================================
REM KONFIGURATION
REM ========================================

REM Input M3U Datei
set INPUT_FILE=playlist.m3u

REM Output Datei
set OUTPUT_FILE=working_streams.m3u

REM Timeout pro Stream (Sekunden)
set TIMEOUT=10

REM Anzahl paralleler Worker
set WORKERS=16

REM Modus: normal / safe / aggressive
set MODE=normal

REM Verbose Ausgabe (1=an, 0=aus)
set VERBOSE=1

REM ========================================

echo Konfiguration:
echo   Input:   %INPUT_FILE%
echo   Output:  %OUTPUT_FILE%
echo   Timeout: %TIMEOUT%s
echo   Worker:  %WORKERS%
echo   Modus:   %MODE%
echo   Verbose: %VERBOSE%
echo.

REM Pruefe ob Python-Skript existiert
if not exist "check_iptv_pro.py" (
    echo [FEHLER] check_iptv_pro.py nicht gefunden!
    echo Bitte speichere das Skript in: %CD%
    echo.
    pause
    exit /b 1
)

REM Pruefe ob Input-Datei existiert
if not exist "%INPUT_FILE%" (
    echo [FEHLER] Input-Datei nicht gefunden: %INPUT_FILE%
    echo.
    pause
    exit /b 1
)

echo ========================================
echo Starte Verarbeitung...
echo ========================================
echo.

REM Baue Kommando zusammen
set CMD=python check_iptv_pro.py "%INPUT_FILE%" -o "%OUTPUT_FILE%" -t %TIMEOUT% -w %WORKERS%

REM Fuege Modus hinzu
if "%MODE%"=="safe" set CMD=%CMD% --safe
if "%MODE%"=="aggressive" set CMD=%CMD% --aggressive

REM Fuege Verbose hinzu
if "%VERBOSE%"=="1" set CMD=%CMD% -v

REM Fuehre aus
%CMD%

echo.
echo ========================================
echo FERTIG!
echo ========================================
echo.

REM Zeige Output-Datei
if exist "%OUTPUT_FILE%" (
    echo Output gespeichert in:
    echo %CD%\%OUTPUT_FILE%
    echo.
    
    REM Zaehle Streams
    for /f %%A in ('findstr /R /C:"^http" "%OUTPUT_FILE%" ^| find /c /v ""') do set STREAM_COUNT=%%A
    echo Funktionierende Streams: %STREAM_COUNT%
    echo.
)

pause