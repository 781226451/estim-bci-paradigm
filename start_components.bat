@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
set "BRIDGE_SCRIPT=%ROOT%lsl_marker_to_uart.py"
set "PATIENT_SCRIPT=%ROOT%patient.py"
set "LOG_DIR=%ROOT%data\component_logs"
set "BRIDGE_STDOUT=%LOG_DIR%\lsl_marker_to_uart.out.log"
set "BRIDGE_STDERR=%LOG_DIR%\lsl_marker_to_uart.err.log"
set "BRIDGE_TITLE=EstimBCI_LSL_UART_Bridge"
set "BRIDGE_STARTUP_WAIT_SECONDS=2"
set "BRIDGE_SHUTDOWN_WAIT_SECONDS=5"

cd /d "%ROOT%" || exit /b 1
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if not exist "%PYTHON%" (
    echo Python venv not found. Running uv sync...
    uv sync
)

if not exist "%PYTHON%" (
    echo Python not found: "%PYTHON%"
    echo Please check whether uv sync completed successfully.
    exit /b 1
)
if not exist "%BRIDGE_SCRIPT%" (
    echo Bridge script not found: "%BRIDGE_SCRIPT%"
    exit /b 1
)
if not exist "%PATIENT_SCRIPT%" (
    echo Patient script not found: "%PATIENT_SCRIPT%"
    exit /b 1
)

del /q "%BRIDGE_STDOUT%" "%BRIDGE_STDERR%" 2>nul

echo Starting LSL-to-UART bridge...
start "%BRIDGE_TITLE%" /min cmd /c ""%PYTHON%" "%BRIDGE_SCRIPT%" > "%BRIDGE_STDOUT%" 2> "%BRIDGE_STDERR%""

timeout /t %BRIDGE_STARTUP_WAIT_SECONDS% /nobreak >nul

if exist "%BRIDGE_STDERR%" (
    findstr /c:"UART setup failed" "%BRIDGE_STDERR%" >nul
    if not errorlevel 1 (
        echo LSL-to-UART bridge failed. Patient app will not start.
        call :show_log "%BRIDGE_STDOUT%" "bridge stdout"
        call :show_log "%BRIDGE_STDERR%" "bridge stderr"
        exit /b 1
    )
)

echo Bridge started.
echo   stdout: "%BRIDGE_STDOUT%"
echo   stderr: "%BRIDGE_STDERR%"
echo Starting patient app...

"%PYTHON%" "%PATIENT_SCRIPT%"
set "PATIENT_EXIT_CODE=%ERRORLEVEL%"

echo Patient app exited. Waiting for bridge shutdown...
timeout /t %BRIDGE_SHUTDOWN_WAIT_SECONDS% /nobreak >nul

tasklist /fi "WINDOWTITLE eq %BRIDGE_TITLE%" 2>nul | findstr /i "cmd.exe" >nul
if not errorlevel 1 (
    echo Bridge did not exit in %BRIDGE_SHUTDOWN_WAIT_SECONDS% seconds. Stopping it.
    taskkill /fi "WINDOWTITLE eq %BRIDGE_TITLE%" /t /f >nul 2>nul
)

call :show_log "%BRIDGE_STDOUT%" "bridge stdout"
call :show_log "%BRIDGE_STDERR%" "bridge stderr"

exit /b %PATIENT_EXIT_CODE%

:show_log
set "LOG_PATH=%~1"
set "LOG_TITLE=%~2"
if exist "%LOG_PATH%" (
    echo.
    echo [%LOG_TITLE%]
    type "%LOG_PATH%"
)
exit /b 0
