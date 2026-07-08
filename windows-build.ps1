<#
.SYNOPSIS
    HanCast 一键构建脚本

.DESCRIPTION
    检查依赖 → 初始化 Python 环境 → Nuitka 编译 Sidecar → 前端构建 → Tauri 打包

.PARAMETER Clean
    清理所有构建产物后重新构建

.EXAMPLE
    .\build.ps1
    .\build.ps1 -Clean
#>

param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Python 镜像源（清华源）
$env:UV_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
$env:UV_EXTRA_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple"

# ============================================================
#  工具函数
# ============================================================

function Write-Step  { param([string]$Msg) Write-Host "  [$args] $Msg" -ForegroundColor Cyan }
function Write-OK    { param([string]$Msg) Write-Host "  [OK] $Msg" -ForegroundColor Green }
function Write-Err   { param([string]$Msg) Write-Host "  [ERROR] $Msg" -ForegroundColor Red }

function Test-Command {
    param([string]$Name)
    $null = Get-Command $Name -ErrorAction SilentlyContinue
    return $?
}

# ============================================================
#  Banner
# ============================================================

Write-Host ""
Write-Host "  ========================================"  -ForegroundColor Yellow
Write-Host "   HanCast Build Script"                       -ForegroundColor Yellow
Write-Host "  ========================================"  -ForegroundColor Yellow
Write-Host ""

# ============================================================
#  检查是否在项目根目录
# ============================================================

if (-not (Test-Path "package.json")) {
    Write-Err "请在项目根目录下运行此脚本"
    Write-Host "  用法: .\build.ps1 [-Clean]"
    exit 1
}

# ============================================================
#  清理（可选）
# ============================================================

if ($Clean) {
    Write-Host "  [CLEAN] 删除构建产物..." -ForegroundColor DarkYellow
    @("macast-backend\dist", "macast-backend\build", "src-tauri\target\release") | ForEach-Object {
        if (Test-Path $_) {
            Remove-Item $_ -Recurse -Force
            Write-Host "    删除 $_" -ForegroundColor DarkGray
        }
    }
    Get-ChildItem "macast-backend\*.spec" -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-OK "已清理"
    Write-Host ""
}

# ============================================================
#  1/4 检查前置依赖
# ============================================================

Write-Step "1/4 检查前置依赖..."

$missing = @()

foreach ($cmd in @("python", "uv", "node", "cargo")) {
    if (-not (Test-Command $cmd)) {
        $missing += $cmd
    }
}

if ($missing.Count -gt 0) {
    Write-Err "缺少以下依赖: $($missing -join ', ')"
    Write-Host ""
    Write-Host "  请安装:"
    Write-Host "    - Python 3.11+  https://www.python.org/downloads/"
    Write-Host "    - uv            https://docs.astral.sh/uv/getting-started/installation/"
    Write-Host "    - Node.js       https://nodejs.org/"
    Write-Host "    - Rust          https://rustup.rs/"
    exit 1
}

# 检查 Python 版本
$pyVer = python --version 2>&1 | Select-String -Pattern "(\d+)\.(\d+)\.(\d+)" | ForEach-Object { $_.Matches[0].Groups[1,2].Value -join "." }
$pyMajor, $pyMinor = $pyVer -split "\." | ForEach-Object { [int]$_ }
if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 11)) {
    $fullVer = python --version 2>&1
    Write-Err "需要 Python 3.11+，当前: $fullVer"
    exit 1
}

$pyFullVer = python --version 2>&1
Write-OK "全部依赖就绪 ($pyFullVer)"
Write-Host ""

# ============================================================
#  2/4 初始化 Python 环境
# ============================================================

Write-Step "2/4 初始化 Python 环境..."

Push-Location macast-backend
try {
    uv sync --all-extras
    if ($LASTEXITCODE -ne 0) { throw "uv sync failed" }
} catch {
    Write-Err "Python 环境初始化失败"
    exit 1
} finally {
    Pop-Location
}

Write-OK "Python 环境就绪"
Write-Host ""

# ============================================================
#  3/4 构建
# ============================================================

Write-Step "3/4 开始构建 HanCast..."
Write-Host ""
Write-Host "    前端     npm run build"                         -ForegroundColor DarkGray
Write-Host "    Sidecar  Nuitka (首次约 5-15 min，之后走缓存)" -ForegroundColor DarkGray
Write-Host "    Tauri    cargo tauri build"                     -ForegroundColor DarkGray
Write-Host ""

cargo tauri build
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Err "构建失败，请检查上方输出"
    exit 1
}

# ============================================================
#  4/4 完成
# ============================================================

Write-Host ""
Write-Host "  ========================================"  -ForegroundColor Green
Write-Host "   构建完成!"                                   -ForegroundColor Green
Write-Host "  ========================================"  -ForegroundColor Green
Write-Host ""
Write-Host "  产物路径: src-tauri\target\release\bundle\"
Write-Host ""
Write-Host "  用法:"
Write-Host "    .\build.ps1          正常构建"
Write-Host "    .\build.ps1 -Clean   清理后重新构建"
Write-Host ""
