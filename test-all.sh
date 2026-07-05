#!/bin/bash
echo ""
echo "========================================"
echo "  Macast-Han Test Suite"
echo "========================================"
echo ""

PASS=0
FAIL=0

echo "[1/4] Python Backend Tests"
echo "----------------------------------------"
cd macast-backend
if ./.venv/Scripts/python.exe -m pytest tests/ -v --tb=short; then
    echo "[PASS] Python tests"; ((PASS++))
else
    echo "[FAIL] Python tests"; ((FAIL++))
fi
cd ..
echo ""

echo "[2/4] Sidecar Communication Test"
echo "----------------------------------------"
cd macast-backend
RESULT=$(echo '{"id":1,"cmd":"get_devices","params":{}}' | ./.venv/Scripts/python.exe -m macast_sidecar.main 2>/dev/null)
if echo "$RESULT" | grep -q '"success": true'; then
    echo "[PASS] Sidecar communication"; ((PASS++))
else
    echo "[FAIL] Sidecar communication"; ((FAIL++))
fi
cd ..
echo ""

echo "[3/4] TypeScript Type Check"
echo "----------------------------------------"
if npx vue-tsc --noEmit; then
    echo "[PASS] TypeScript type check"; ((PASS++))
else
    echo "[FAIL] TypeScript type check"; ((FAIL++))
fi
echo ""

echo "[4/4] Frontend Build"
echo "----------------------------------------"
if npx vite build; then
    echo "[PASS] Frontend build"; ((PASS++))
else
    echo "[FAIL] Frontend build"; ((FAIL++))
fi
echo ""

echo "========================================"
echo "  Results: $PASS passed, $FAIL failed"
echo "========================================"
echo ""

[ $FAIL -eq 0 ]
