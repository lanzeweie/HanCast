@echo off
chcp 65001 >nul 2>&1

echo.
echo ========================================
echo   HanCast Test Suite
echo ========================================
echo.

set PASS=0
set FAIL=0

echo [1/5] Python Backend Tests
echo ----------------------------------------
cd hancast-backend
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

echo [2/5] Sidecar Communication Test
echo ----------------------------------------
cd hancast-backend
echo {"id":1,"cmd":"get_devices","params":{}} | .venv\Scripts\python.exe -m hancast_sidecar.main 2>nul
if %ERRORLEVEL% EQU 0 (
    echo [PASS] Sidecar communication
    set /a PASS+=1
) else (
    echo [FAIL] Sidecar communication
    set /a FAIL+=1
)
cd ..
echo.

echo [3/5] TypeScript Type Check
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

echo [4/5] Frontend Build
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

echo [5/5] Rust Build
echo ----------------------------------------
cd src-tauri
call cargo build
if %ERRORLEVEL% EQU 0 (
    echo [PASS] Rust build
    set /a PASS+=1
) else (
    echo [FAIL] Rust build
    set /a FAIL+=1
)
cd ..
echo.

echo ========================================
echo   Results: %PASS% passed, %FAIL% failed
echo ========================================
echo.

if %FAIL% GTR 0 exit /b 1
exit /b 0
