@echo off
chcp 65001 >nul 2>&1

echo.
echo ========================================
echo   Macast-Han Test Suite
echo ========================================
echo.

set PASS=0
set FAIL=0

echo [1/4] Python Backend Tests
echo ----------------------------------------
cd macast-backend
call .venv\Scripts\python.exe -m pytest tests/ -v --tb=short
if %ERRORLEVEL% EQU 0 (
    echo [PASS] Python tests
    set /a PASS+=1
) else (
    echo [FAIL] Python tests
    set /a FAIL+=1
)
cd ..
echo.

echo [2/4] Sidecar Communication Test
echo ----------------------------------------
cd macast-backend
echo {"id":1,"cmd":"get_devices","params":{}} | .venv\Scripts\python.exe -m macast_sidecar.main 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [PASS] Sidecar communication
    set /a PASS+=1
) else (
    echo [FAIL] Sidecar communication
    set /a FAIL+=1
)
cd ..
echo.

echo [3/4] TypeScript Type Check
echo ----------------------------------------
call npx vue-tsc --noEmit
if %ERRORLEVEL% EQU 0 (
    echo [PASS] TypeScript type check
    set /a PASS+=1
) else (
    echo [FAIL] TypeScript type check
    set /a FAIL+=1
)
echo.

echo [4/4] Frontend Build
echo ----------------------------------------
call npx vite build
if %ERRORLEVEL% EQU 0 (
    echo [PASS] Frontend build
    set /a PASS+=1
) else (
    echo [FAIL] Frontend build
    set /a FAIL+=1
)
echo.

echo ========================================
echo   Results: %PASS% passed, %FAIL% failed
echo ========================================
echo.

if %FAIL% GTR 0 exit /b 1
exit /b 0
