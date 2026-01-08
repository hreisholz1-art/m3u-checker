@echo off
setlocal

:: Hole das aktuelle Verzeichnis der Batch-Datei
set "CurrentDir=%~dp0"

:: Starte CMD als Admin mit dem aktuellen Verzeichnis
powershell -Command "Start-Process cmd -ArgumentList '/k cd /d \"%CurrentDir%\"' -Verb RunAs"

endlocal