@echo off
title Detener Descargador TOTVS
cd /d "%~dp0"

echo ==========================================================
echo   DETENIENDO BUCLE DEL DESCARGADOR TOTVS
echo ==========================================================
echo.

set PID_FILE=logs_descarga\downloader.pid

if exist "%PID_FILE%" (
    set /p PID=<"%PID_FILE%"
    echo Encontrado proceso con PID: %PID%
    taskkill /F /PID %PID% 2>nul
    del "%PID_FILE%" 2>nul
    echo [OK] Proceso detenido exitosamente.
) else (
    echo No se encontro archivo de PID. Intentando detener por nombre...
    taskkill /F /IM python.exe /FI "WINDOWTITLE eq TOTVS*" 2>nul
    echo Si sigue corriendo, puedes cerrar el proceso en el Administrador de tareas.
)

echo.
pause
