@echo off
setlocal EnableDelayedExpansion
title Headroom Toggle

:: ─── Config ───
set "PROXY_PORT=8787"
set "PROXY_URL=http://127.0.0.1:%PROXY_PORT%"
set "HEADROOM_EXE=C:\laragon\bin\python\python-3.10\Scripts\headroom.exe"

:: ─── Route subcommand ───
if "%~1"=="on"     goto :CMD_ON
if "%~1"=="off"    goto :CMD_OFF
if "%~1"=="status" goto :CMD_STATUS
if "%~1"==""       goto :CMD_TOGGLE
goto :USAGE

:: ═══════════════════════════════════════
:CMD_TOGGLE
:: ═══════════════════════════════════════
curl -s -o nul -w "" "%PROXY_URL%/health" >nul 2>&1
if %errorlevel% equ 0 (
    goto :CMD_OFF
) else (
    goto :CMD_ON
)

:: ═══════════════════════════════════════
:CMD_ON
:: ═══════════════════════════════════════
curl -s -o nul "%PROXY_URL%/health" >nul 2>&1
if %errorlevel% equ 0 (
    echo [Headroom] Already running on %PROXY_URL%
    goto :SHOW_STATUS
)

echo [Headroom] Starting proxy on port %PROXY_PORT% ...
start "Headroom Proxy" /min cmd /c ""%HEADROOM_EXE%" proxy --no-telemetry --code-aware --port %PROXY_PORT%"

:: Wait for proxy to be ready
set "TRIES=0"
:WAIT_LOOP
if !TRIES! geq 15 (
    echo [Headroom] ERROR: Proxy did not start within 15 seconds.
    goto :EOF
)
timeout /t 1 /nobreak >nul
curl -s -o nul "%PROXY_URL%/health" >nul 2>&1
if %errorlevel% neq 0 (
    set /a TRIES+=1
    goto :WAIT_LOOP
)

:: Set user env var so new Claude Code sessions pick it up
powershell -Command "[System.Environment]::SetEnvironmentVariable('ANTHROPIC_BASE_URL','%PROXY_URL%','User')"
set "ANTHROPIC_BASE_URL=%PROXY_URL%"

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   HEADROOM: ON                                  ║
echo  ║   Proxy:    %PROXY_URL%              ║
echo  ║   Stats:    %PROXY_URL%/stats        ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Claude Code sessions started AFTER this point
echo  will route through Headroom automatically.
echo.
echo  Restart VSCode or open a new terminal to apply.
echo  To stop:  headroom off
goto :EOF

:: ═══════════════════════════════════════
:CMD_OFF
:: ═══════════════════════════════════════
curl -s -o nul "%PROXY_URL%/health" >nul 2>&1
if %errorlevel% neq 0 (
    echo [Headroom] Not running. Nothing to stop.
    :: Clean up env var just in case
    powershell -Command "[System.Environment]::SetEnvironmentVariable('ANTHROPIC_BASE_URL', $null, 'User')"
    goto :EOF
)

echo [Headroom] Stopping proxy ...

:: Kill the headroom proxy process
powershell -Command "Get-Process -Name 'headroom' -ErrorAction SilentlyContinue | Stop-Process -Force"
:: Also kill the wrapper cmd window
powershell -Command "Get-Process -Name 'cmd' -ErrorAction SilentlyContinue | Where-Object { $_.MainWindowTitle -like 'Headroom Proxy*' } | Stop-Process -Force"

:: Remove user env var
powershell -Command "[System.Environment]::SetEnvironmentVariable('ANTHROPIC_BASE_URL', $null, 'User')"
set "ANTHROPIC_BASE_URL="

timeout /t 1 /nobreak >nul

echo.
echo  ╔══════════════════════════════════════════════════╗
echo  ║   HEADROOM: OFF                                 ║
echo  ║   Proxy stopped. Env var removed.               ║
echo  ╚══════════════════════════════════════════════════╝
echo.
echo  Claude Code will connect directly to Anthropic API.
echo  Restart VSCode or open a new terminal to apply.
goto :EOF

:: ═══════════════════════════════════════
:CMD_STATUS
:: ═══════════════════════════════════════
:SHOW_STATUS
echo.
echo  ── Headroom Status ──
echo.

curl -s -o nul "%PROXY_URL%/health" >nul 2>&1
if %errorlevel% equ 0 (
    echo  Proxy:     RUNNING on %PROXY_URL%
) else (
    echo  Proxy:     STOPPED
)

for /f "usebackq tokens=*" %%A in (`powershell -Command "[System.Environment]::GetEnvironmentVariable('ANTHROPIC_BASE_URL','User')"`) do set "USER_ENV=%%A"
if defined USER_ENV (
    echo  Env var:   ANTHROPIC_BASE_URL = %USER_ENV%
) else (
    echo  Env var:   ANTHROPIC_BASE_URL = (not set)
)

curl -s -o nul "%PROXY_URL%/health" >nul 2>&1
if %errorlevel% equ 0 (
    echo.
    echo  ── Compression Stats ──
    echo.
    curl -s "%PROXY_URL%/stats" 2>nul
    echo.
)
goto :EOF

:: ═══════════════════════════════════════
:USAGE
:: ═══════════════════════════════════════
echo.
echo  Usage: headroom [command]
echo.
echo  Commands:
echo    (none)     Toggle on/off automatically
echo    on         Start proxy + set env var
echo    off        Stop proxy + remove env var
echo    status     Show current state + stats
echo.
goto :EOF
