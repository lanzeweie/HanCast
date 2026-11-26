#!/bin/bash
echo ""
echo "========================================"
echo "  HanCast Test Suite"
echo "========================================"
echo ""

PASS=0
FAIL=0

# 解析 Python 解释器：优先复用 uv 创建的虚拟环境（Windows / Unix 路径不同）
PYTHON_CMD=()
if [ -x ./.venv/bin/python ]; then
    PYTHON_CMD=(./.venv/bin/python)
elif [ -x ./.venv/Scripts/python.exe ]; then
    PYTHON_CMD=(./.venv/Scripts/python.exe)
elif command -v uv >/dev/null 2>&1; then
    PYTHON_CMD=(uv run python)
else
    PYTHON_CMD=(python3)
fi

echo "[1/5] Python Backend Tests"
echo "----------------------------------------"
cd hancast-backend
if "${PYTHON_CMD[@]}" -m pytest tests/ -v --tb=short; then
    echo "[PASS] Python tests"; ((PASS++))
else
    echo "[FAIL] Python tests"; ((FAIL++))
fi
cd ..
echo ""

echo "[2/5] Sidecar Communication Test"
echo "----------------------------------------"
cd hancast-backend
RESULT=$(echo '{"id":1,"cmd":"get_devices","params":{}}' | "${PYTHON_CMD[@]}" -m hancast_sidecar.main 2>/dev/null)
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
# 与 `npm run tauri dev` 一致：开发构建不校验打包用的 sidecar/mpv 资源
if TAURI_CONFIG='{"bundle":{"externalBin":[],"resources":[]}}' cargo build; then
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
