#!/usr/bin/env bash
#
# HanCast 构建脚本 (macOS)
#
# 流程与 windows-build.ps1 对齐：
#   依赖检查 → npm install → uv sync → 构建 Nuitka sidecar → 准备 mpv.app
#   → 递归签名 sidecar/mpv → tauri build（app + dmg）→ 校验产物
#
# 首版仅支持 Apple Silicon (aarch64-apple-darwin)。Nuitka 产物和 mpv.app
# 都是架构绑定的，Intel 需要单独构建。
#
# 用法:
#   ./mac-build.sh                          # 增量构建
#   ./mac-build.sh --rebuild-sidecar        # 强制重编 Python 后端
#   ./mac-build.sh --clean-cache            # 清理 Rust release 缓存
#   ./mac-build.sh --skip-sidecar --skip-mpv
#   ./mac-build.sh --no-dmg                 # 只出 .app
#   ./mac-build.sh --download-mpv           # 下载固定的自包含 mpv.app 到 vendor/
#
# 环境变量:
#   SIGN_IDENTITY   签名身份，默认 "-"（ad-hoc）。正式发版填
#                   "Developer ID Application: xxx (TEAMID)"。
#   HARDENED        1/0 强制开关 Hardened Runtime；默认 ad-hoc 关闭、
#                   Developer ID 开启。
#   MPV_APP_SRC     自包含 mpv.app 路径；默认依次查找
#                   vendor/mpv.app、vendor/ 下的 mpv tarball、/Applications/mpv.app。
#   MPV_CONFIG_SRC  portable_config 源目录；默认仓库根目录 mpv/portable_config。
#   SKIP_SIGN       1 跳过嵌套签名（仅本地调试）。
#
# 公证（可选，正式发版）：导出 Tauri 支持的环境变量后重新运行脚本，
# Tauri 会在打包时自动提交公证并 staple：
#   APPLE_ID / APPLE_PASSWORD / APPLE_TEAM_ID
#   或 APPLE_API_KEY / APPLE_API_KEY_PATH / APPLE_API_ISSUER
#

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

TARGET_TRIPLE="aarch64-apple-darwin"
SIDECAR_DIR="src-tauri/hancast-sidecar"
SIDECAR_OUT="$SIDECAR_DIR/hancast-sidecar-$TARGET_TRIPLE"
MPV_DIR="src-tauri/mpv"
APP_PATH="src-tauri/target/release/bundle/macos/HanCast.app"
DMG_DIR="src-tauri/target/release/bundle/dmg"

SIGN_IDENTITY="${SIGN_IDENTITY:--}"
SKIP_SIGN="${SKIP_SIGN:-0}"
# 与 tauri.macos.conf.json 保持一致，避免两边写死后漂移
MIN_MACOS="$(node -p "require('./src-tauri/tauri.macos.conf.json').bundle.macOS.minimumSystemVersion" 2>/dev/null || echo '14.0')"
REBUILD_SIDECAR=0
CLEAN_CACHE=0
SKIP_SIDECAR=0
SKIP_MPV=0
NO_DMG=0
DOWNLOAD_MPV=0

# 固定版本的第三方自包含 arm64 构建（macOS 14+）。
MPV_TARBALL="mpv-arm64-0.40.0.tar.gz"
MPV_TARBALL_URL="https://laboratory.stolendata.net/~djinn/mpv_osx/$MPV_TARBALL"
MPV_TARBALL_SHA256="3170fb709defebaba33e9755297d70dc3562220541de54fc3d494a8309ef1260"

# ============================================================
#  工具函数
# ============================================================

C_RESET='\033[0m'; C_CYAN='\033[0;36m'; C_GREEN='\033[0;32m'
C_YELLOW='\033[0;33m'; C_RED='\033[0;31m'; C_DIM='\033[2m'

step()  { printf "\n  ${C_CYAN}[%s] %s${C_RESET}\n  %s\n" "$1" "$2" "$(printf -- '-%.0s' {1..50})"; }
ok()    { printf "  ${C_GREEN}[OK]${C_RESET} %s\n" "$1"; }
warn()  { printf "  ${C_YELLOW}[WARN]${C_RESET} %s\n" "$1"; }
err()   { printf "  ${C_RED}[ERROR]${C_RESET} %s\n" "$1" >&2; }
dim()   { printf "  ${C_DIM}%s${C_RESET}\n" "$1"; }

die() { err "$1"; exit 1; }

usage() {
  sed -n '2,60p' "$ROOT/mac-build.sh" | sed 's/^# \{0,1\}//'
  exit 0
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --rebuild-sidecar) REBUILD_SIDECAR=1 ;;
    --clean-cache)     CLEAN_CACHE=1 ;;
    --skip-sidecar)    SKIP_SIDECAR=1 ;;
    --skip-mpv)        SKIP_MPV=1 ;;
    --no-dmg)          NO_DMG=1 ;;
    --download-mpv)    DOWNLOAD_MPV=1 ;;
    -h|--help)         usage ;;
    *)                 die "未知参数: $1（--help 查看用法）" ;;
  esac
  shift
done

if [[ "$SIGN_IDENTITY" == "-" ]]; then
  HARDENED="${HARDENED:-0}"
else
  HARDENED="${HARDENED:-1}"
fi

# ============================================================
#  横幅
# ============================================================

printf "\n"
printf "  ========================================\n"
printf "   HanCast 构建脚本 (macOS)\n"
printf "  ========================================\n"

# ============================================================
#  Step 1: 前置检查
# ============================================================

step "1" "检查前置依赖..."

[[ "$(uname -s)" == "Darwin" ]] || die "此脚本只能在 macOS 上运行"
if [[ "$(uname -m)" != "arm64" && "${ALLOW_NON_ARM64:-0}" != "1" ]]; then
  die "首版仅支持 Apple Silicon (arm64)。Intel 需要单独构建；确需继续请设置 ALLOW_NON_ARM64=1"
fi

[[ -f package.json && -f src-tauri/Cargo.toml ]] || die "请在项目根目录运行此脚本"

missing=()
for cmd in node npm uv cargo rustc codesign otool file ditto; do
  command -v "$cmd" >/dev/null 2>&1 || missing+=("$cmd")
done
[[ ${#missing[@]} -eq 0 ]] || die "缺少依赖: ${missing[*]}"

node_ver="$(node --version)"
cargo_ver="$(rustc --version | awk '{print $2}')"
ok "依赖就绪 (node $node_ver, rustc $cargo_ver, 架构 $(uname -m))"

# ============================================================
#  Step 2: 前端依赖
# ============================================================

step "2" "安装前端依赖..."
npm install --no-audit --no-fund
ok "前端依赖就绪"

# ============================================================
#  Step 3: Python 环境
# ============================================================

step "3" "初始化 Python 环境..."
( cd hancast-backend && uv sync --all-extras )
ok "Python 环境就绪"

# ============================================================
#  Step 4: 清理 Rust 缓存（可选）
# ============================================================

if [[ "$CLEAN_CACHE" == "1" ]]; then
  step "4" "清理 Rust release 缓存..."
  rm -rf src-tauri/target/release
  ok "已清理 src-tauri/target/release"
else
  step "4" "跳过 Rust 缓存清理"
fi

# ============================================================
#  Step 5: 构建 Python Sidecar
# ============================================================

step "5" "构建 Python Sidecar..."

if [[ "$SKIP_SIDECAR" == "1" ]]; then
  [[ -x "$SIDECAR_OUT" ]] || die "跳过构建但找不到 sidecar: $SIDECAR_OUT"
  ok "使用已有 sidecar: $SIDECAR_OUT"
else
  sidecar_args=(--force)
  [[ "$REBUILD_SIDECAR" == "1" ]] || sidecar_args=()
  ( cd hancast-backend && uv run python scripts/build_sidecar.py "${sidecar_args[@]}" )
  [[ -x "$SIDECAR_OUT" ]] || die "Sidecar 构建产物不存在: $SIDECAR_OUT"
  chmod +x "$SIDECAR_OUT"
  ok "Sidecar 就绪: $SIDECAR_OUT"
fi

sidecar_arch="$(lipo -archs "$SIDECAR_OUT" 2>/dev/null || true)"
[[ "$sidecar_arch" == *arm64* ]] || die "Sidecar 不是 arm64 产物（lipo: ${sidecar_arch:-unknown}）"

# ============================================================
#  Step 6: 准备 mpv.app（整包，不拆二进制）
# ============================================================

step "6" "准备 mpv.app..."

find_mpv_app() {
  local candidate
  for candidate in \
    "${MPV_APP_SRC:-}" \
    "$ROOT/vendor/mpv.app" \
    "/Applications/mpv.app" \
    "$HOME/Applications/mpv.app"; do
    [[ -n "$candidate" ]] || continue
    if [[ -d "$candidate" && -x "$candidate/Contents/MacOS/mpv" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  done

  # vendor/ 下解压好的 tarball
  local tarball
  tarball="$(find "$ROOT/vendor" -maxdepth 1 -name 'mpv*arm64*.tar.gz' 2>/dev/null | head -1 || true)"
  if [[ -n "$tarball" ]]; then
    local stage="$ROOT/vendor/.mpv-extract"
    rm -rf "$stage"; mkdir -p "$stage"
    tar -xzf "$tarball" -C "$stage"
    candidate="$(find "$stage" -maxdepth 3 -name mpv.app -type d | head -1 || true)"
    if [[ -n "$candidate" && -x "$candidate/Contents/MacOS/mpv" ]]; then
      printf '%s\n' "$candidate"
      return 0
    fi
  fi
  return 1
}

if [[ "$DOWNLOAD_MPV" == "1" ]]; then
  mkdir -p "$ROOT/vendor"
  if [[ ! -f "$ROOT/vendor/$MPV_TARBALL" ]]; then
    dim "下载 $MPV_TARBALL ..."
    curl -fL --retry 3 -o "$ROOT/vendor/$MPV_TARBALL" "$MPV_TARBALL_URL"
  fi
  actual_sha="$(shasum -a 256 "$ROOT/vendor/$MPV_TARBALL" | awk '{print $1}')"
  [[ "$actual_sha" == "$MPV_TARBALL_SHA256" ]] \
    || die "mpv tarball 校验失败: $actual_sha"
  ok "mpv tarball 校验通过"
fi

if [[ "$SKIP_MPV" == "1" ]]; then
  [[ -x "$MPV_DIR/mpv.app/Contents/MacOS/mpv" ]] || die "跳过准备但找不到 $MPV_DIR/mpv.app"
  ok "使用已有 $MPV_DIR/mpv.app"
else
  mpv_src="$(find_mpv_app || true)"
  [[ -n "$mpv_src" ]] || die "找不到自包含 mpv.app。请设置 MPV_APP_SRC、放到 vendor/，或加 --download-mpv（mpv.io/installation 有第三方构建）"

  dim "源: $mpv_src"
  rm -rf "$MPV_DIR"
  mkdir -p "$MPV_DIR"
  # ditto 保留符号链接、权限和扩展属性，比 cp -R 更适合 .app
  ditto "$mpv_src" "$MPV_DIR/mpv.app"
  ok "mpv.app 已复制到 $MPV_DIR/mpv.app"
fi

MPV_BIN="$MPV_DIR/mpv.app/Contents/MacOS/mpv"
[[ -x "$MPV_BIN" ]] || die "mpv 可执行文件不存在: $MPV_BIN"

mpv_arch="$(lipo -archs "$MPV_BIN" 2>/dev/null || true)"
[[ "$mpv_arch" == *arm64* ]] || die "mpv.app 不是 arm64 构建（lipo: ${mpv_arch:-unknown}）"

# 不能引用 Homebrew / 本机绝对路径，否则换一台 Mac 就打不开
dim "检查 mpv 动态库引用..."
bad_refs=0
while IFS= read -r -d '' f; do
  file -b "$f" | grep -q "Mach-O" || continue
  while IFS= read -r line; do
    case "$line" in
      /opt/homebrew/*|/usr/local/*)
        err "mpv 引用了本机路径: $line"
        err "  来自: ${f#"$MPV_DIR"/}"
        bad_refs=1
        ;;
    esac
  done < <(otool -L "$f" 2>/dev/null | tail -n +2)
done < <(find "$MPV_DIR/mpv.app" -type f -print0)

[[ "$bad_refs" == "0" ]] || die "mpv.app 不是自包含构建，不能分发（请换官方/第三方静态构建）"
ok "mpv.app 自包含检查通过"

# 真正的系统下限看 Mach-O 的 LC_BUILD_VERSION/minos；Info.plist 里通常没有。
mpv_min="$(vtool -show-build "$MPV_BIN" 2>/dev/null | awk '/minos/ {print $2; exit}' || true)"
if [[ -z "$mpv_min" ]]; then
  mpv_min="$(/usr/libexec/PlistBuddy -c 'Print :LSMinimumSystemVersion' \
    "$MPV_DIR/mpv.app/Contents/Info.plist" 2>/dev/null || true)"
fi
if [[ -n "$mpv_min" ]]; then
  dim "mpv 最低系统版本: $mpv_min（Tauri 配置为 $MIN_MACOS）"
  mpv_major="${mpv_min%%.*}"
  min_major="${MIN_MACOS%%.*}"
  if [[ "$mpv_major" =~ ^[0-9]+$ && "$min_major" =~ ^[0-9]+$ ]] && (( mpv_major > min_major )); then
    warn "mpv.app 要求 macOS $mpv_min，高于 Tauri 配置的 $MIN_MACOS；低于 $mpv_min 的系统上 MPV 无法启动"
    warn "要么更换支持 macOS $MIN_MACOS 的 mpv 构建，要么把 minimumSystemVersion 提高到 $mpv_min"
  fi
fi

# portable_config：存在才同步；缺失时保留空目录，让 MPV 走默认配置
if [[ -n "${MPV_CONFIG_SRC:-}" && -d "${MPV_CONFIG_SRC:-}" ]]; then
  ditto "$MPV_CONFIG_SRC" "$MPV_DIR/portable_config"
  ok "portable_config 已同步（$MPV_CONFIG_SRC）"
elif [[ -d "$ROOT/mpv/portable_config" ]]; then
  ditto "$ROOT/mpv/portable_config" "$MPV_DIR/portable_config"
  ok "portable_config 已同步（$ROOT/mpv/portable_config）"
else
  mkdir -p "$MPV_DIR/portable_config"
  warn "未找到 portable_config，macOS 将使用 MPV 默认配置"
fi

# ============================================================
#  Step 7: 递归签名（sidecar → mpv.app；外层 .app 由 Tauri 签）
# ============================================================

sign_file() {
  local file="$1" entitlements="${2:-}"
  [[ -f "$file" ]] || return 0
  file -b "$file" | grep -q "Mach-O" || return 0

  local args=(--force --sign "$SIGN_IDENTITY")
  if [[ "$SIGN_IDENTITY" == "-" ]]; then
    args+=(--timestamp=none)
  else
    args+=(--timestamp)
  fi
  [[ "$HARDENED" == "1" ]] && args+=(--options runtime)
  [[ -n "$entitlements" ]] && args+=(--entitlements "$entitlements")
  codesign "${args[@]}" "$file"
}

sign_sidecar() {
  local ent="$ROOT/src-tauri/entitlements/sidecar.entitlements"
  dim "签名 sidecar 依赖..."
  while IFS= read -r -d '' f; do
    [[ "$f" == "$SIDECAR_OUT" ]] && continue
    sign_file "$f"
  done < <(find "$SIDECAR_DIR" -type f -print0)

  dim "签名 sidecar 主二进制..."
  sign_file "$SIDECAR_OUT" "$ent"
  codesign --verify --strict "$SIDECAR_OUT"
  ok "sidecar 签名完成"
}

sign_mpv_app() {
  local app="$MPV_DIR/mpv.app"
  local ent="$ROOT/src-tauri/entitlements/mpv.entitlements"

  dim "签名 mpv.app 内的 dylib/so..."
  while IFS= read -r -d '' f; do
    sign_file "$f"
  done < <(find "$app" -type f \( -name '*.dylib' -o -name '*.so' \) -print0)

  dim "签名 mpv.app 内的框架..."
  local ts=(--timestamp=none)
  [[ "$SIGN_IDENTITY" != "-" ]] && ts=(--timestamp)
  while IFS= read -r -d '' fw; do
    codesign --force --sign "$SIGN_IDENTITY" "${ts[@]}" "$fw"
  done < <(find "$app/Contents/Frameworks" -depth -name '*.framework' -type d -print0 2>/dev/null || true)

  dim "签名 mpv 主程序..."
  sign_file "$app/Contents/MacOS/mpv" "$ent"

  dim "签名 mpv.app 外壳..."
  local args=(--force --sign "$SIGN_IDENTITY")
  [[ "$SIGN_IDENTITY" == "-" ]] && args+=(--timestamp=none) || args+=(--timestamp)
  [[ "$HARDENED" == "1" ]] && args+=(--options runtime --entitlements "$ent")
  codesign "${args[@]}" "$app"

  codesign --verify --deep --strict "$app"
  ok "mpv.app 签名完成"
}

if [[ "$SKIP_SIGN" == "1" ]]; then
  step "7" "跳过嵌套签名（SKIP_SIGN=1）"
else
  step "7" "递归签名 (identity: $SIGN_IDENTITY, hardened: $HARDENED)..."
  command -v codesign >/dev/null || die "找不到 codesign"
  sign_sidecar
  sign_mpv_app
fi

# ============================================================
#  Step 8: 前端构建 + Tauri 打包（app + dmg）
# ============================================================

step "8" "前端构建 + Tauri 打包..."

tauri_args=(--bundles app)
[[ "$NO_DMG" == "1" ]] || tauri_args=(--bundles app,dmg)

# 正式签名时覆盖 tauri.macos.conf.json 里的 ad-hoc 默认值
if [[ "$SIGN_IDENTITY" != "-" ]]; then
  esc_identity="${SIGN_IDENTITY//\\/\\\\}"
  esc_identity="${esc_identity//\"/\\\"}"
  tauri_args+=(--config "{\"bundle\":{\"macOS\":{\"signingIdentity\":\"$esc_identity\",\"hardenedRuntime\":true}}}")
fi

export APPLE_SIGNING_IDENTITY="$SIGN_IDENTITY"
dim "tauri build ${tauri_args[*]}"
npm run tauri build -- "${tauri_args[@]}"

[[ -d "$APP_PATH" ]] || die "构建产物不存在: $APP_PATH"
ok "Tauri 打包完成"

# ============================================================
#  Step 9: 产物校验
# ============================================================

step "9" "校验产物..."

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
ok "外层 .app 签名校验通过"

app_size="$(du -sh "$APP_PATH" | awk '{print $1}')"
dim "HanCast.app: $app_size"
dim "  $(defaults read "$ROOT/$APP_PATH/Contents/Info.plist" CFBundleShortVersionString 2>/dev/null || echo 'unknown')"
dim "  LSMinimumSystemVersion: $(defaults read "$ROOT/$APP_PATH/Contents/Info.plist" LSMinimumSystemVersion 2>/dev/null || echo 'unknown')"

if [[ "$SIGN_IDENTITY" == "-" ]]; then
  warn "当前为 ad-hoc 签名：本机可用，分发给其他 Mac 仍需用户手动放行"
  warn "正式发版请设置 SIGN_IDENTITY=Developer ID 并配置公证环境变量"
fi

# ============================================================
#  完成
# ============================================================

printf "\n"
printf "  ========================================\n"
printf "   构建完成！\n"
printf "  ========================================\n\n"
printf "  输出:\n"
printf "    App:  %s\n" "$APP_PATH"
if [[ "$NO_DMG" != "1" ]]; then
  dmg_path="$(find "$DMG_DIR" -maxdepth 1 -name '*.dmg' -type f -print 2>/dev/null | head -1 || true)"
  if [[ -n "$dmg_path" ]]; then
    printf "    DMG:  %s (%s)\n" "$dmg_path" "$(du -sh "$dmg_path" | awk '{print $1}')"
  else
    warn "未找到 DMG，请检查上方 Tauri 输出"
  fi
fi
printf "\n"