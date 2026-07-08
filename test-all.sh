#!/bin/bash
echo ""
echo "========================================"
echo "  HanCast Test Suite"
echo "========================================"
echo ""

PASS=0
FAIL=0

echo "[1/5] Python Backend Tests"
echo "----------------------------------------"
cd hancast-backend
if ./.venv/Scripts/python.exe -m pytest tests/ -v --tb=short; then
    echo "[PASS] Python tests"; ((PASS++))
else
    echo "[FAIL] Python tests"; ((FAIL++))
fi
cd ..
echo ""

echo "[2/5] Sidecar Communication Test"
echo "----------------------------------------"
cd hancast-backend
RESULT=$(echo '{"id":1,"cmd":"get_devices","params":{}}' | ./.venv/Scripts/python.exe -m hancast_sidecar.main 2>/dev/null)
if echo "$RESULT" | grep -q '"success": true'; then
    echo "[PASS] Sidecar communication"; ((PASS++))
else
    echo "[FAIL] Sidecar communication"; ((FAIL++))
fi
cd ..
echo ""

echo "[3/5] TypeScript Type Check"
echo "----------------------------------------"
if npx vue-tsc --noEmit; then
    echo "[PASS] TypeScript type check"; ((PASS++))
else
    echo "[FAIL] TypeScript type check"; ((FAIL++))
fi
echo ""

echo "[4/5] Frontend Build"
echo "----------------------------------------"
if npx vite build; then
    echo "[PASS] Frontend build"; ((PASS++))
else
    echo "[FAIL] Frontend build"; ((FAIL++))
fi
echo ""

echo "[5/5] Rust Build"
echo "----------------------------------------"
cd src-tauri
if cargo build; then
    echo "[PASS] Rust build"; ((PASS++))
else
    echo "[FAIL] Rust build"; ((FAIL++))
fi
cd ..
echo ""

echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"
echo ""

[ $FAIL -eq 0 ]
