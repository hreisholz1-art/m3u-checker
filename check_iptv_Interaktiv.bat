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
REM INTERAKTIVE EINGABE
REM ========================================

:INPUT_FILE_PROMPT
echo.
set /p INPUT_FILE="Input M3U Datei (z.B. 2.m3u): "

if "%INPUT_FILE%"=="" (
    echo [FEHLER] Keine Datei angegeben!
    goto INPUT_FILE_PROMPT
)

if not exist "%INPUT_FILE%" (
    echo [FEHLER] Datei nicht gefunden: %INPUT_FILE%
    goto INPUT_FILE_PROMPT
)

echo.
set /p OUTPUT_FILE="Output Datei (z.B. clean.m3u): "

if "%OUTPUT_FILE%"=="" (
    set OUTPUT_FILE=working_streams.m3u
    echo Verwende Standard: %OUTPUT_FILE%
)

echo.
echo Optionale Einstellungen (Enter fuer Defaults):
echo.

set /p WORKERS="Anzahl Worker [16]: "
if "%WORKERS%"=="" set WORKERS=16

set /p TIMEOUT="Timeout Sekunden [10]: "
if "%TIMEOUT%"=="" set TIMEOUT=10

echo.
echo Modi: 1=Normal  2=Safe (mit Fake-Check)  3=Aggressive (strenger OCR)
set /p MODE_CHOICE="Modus [1]: "
if "%MODE_CHOICE%"=="" set MODE_CHOICE=1

if "%MODE_CHOICE%"=="1" set MODE=normal
if "%MODE_CHOICE%"=="2" set MODE=safe
if "%MODE_CHOICE%"=="3" set MODE=aggressive

set /p VERBOSE="Detaillierte Ausgabe? (J/N) [J]: "
if "%VERBOSE%"=="" set VERBOSE=J

REM ========================================
REM ZUSAMMENFASSUNG
REM ========================================

echo.
echo ========================================
echo KONFIGURATION
echo ========================================
echo Input:   %INPUT_FILE%
echo Output:  %OUTPUT_FILE%
echo Timeout: %TIMEOUT%s
echo Worker:  %WORKERS%
echo Modus:   %MODE%
if /i "%VERBOSE%"=="J" echo Verbose: An
if /i "%VERBOSE%"=="N" echo Verbose: Aus
echo ========================================
echo.

set /p CONFIRM="Starten? (J/N) [J]: "
if "%CONFIRM%"=="" set CONFIRM=J
if /i not "%CONFIRM%"=="J" (
    echo Abgebrochen.
    pause
    exit /b 0
)

echo.
echo Starte Verarbeitung...
echo.

REM ========================================
REM PYTHON-AUFRUF
REM ========================================

set CMD=python check_iptv_pro.py "%INPUT_FILE%" -o "%OUTPUT_FILE%" -t %TIMEOUT% -w %WORKERS%

if "%MODE%"=="safe" set CMD=%CMD% --safe
if "%MODE%"=="aggressive" set CMD=%CMD% --aggressive
if /i "%VERBOSE%"=="J" set CMD=%CMD% -v

%CMD%

REM ========================================
REM ERGEBNIS
REM ========================================

echo.
echo ========================================
echo FERTIG!
echo ========================================
echo.

if exist "%OUTPUT_FILE%" (
    echo Output gespeichert:
    echo %CD%\%OUTPUT_FILE%
    echo.
    
    for /f %%A in ('findstr /R /C:"^http" "%OUTPUT_FILE%" ^| find /c /v ""') do set STREAM_COUNT=%%A
    echo Funktionierende Streams: %STREAM_COUNT%
    echo.
    
    set /p OPEN="Datei oeffnen? (J/N) [N]: "
    if /i "%OPEN%"=="J" start notepad "%OUTPUT_FILE%"
)

pause