<#
.SYNOPSIS
    HanCast 构建脚本 (Windows)

.DESCRIPTION
    检查依赖 → 初始化 Python → Nuitka 构建 Sidecar → 前端构建 → Tauri 打包
    无参数运行时进入交互式问答，带参数时直接执行（适合 CI/自动化）。

.PARAMETER Clean
    构建前清理所有构建产物

.PARAMETER SkipSidecar
    跳过 Nuitka Sidecar 构建（仅前端/Rust 变更时加速）

.PARAMETER ForceSidecar
    强制重新构建 Sidecar（忽略缓存）

.PARAMETER Portable
    构建后打包绿色版

.EXAMPLE
    .\windows-build.ps1                   交互式模式
    .\windows-build.ps1 -Clean            清理后重新构建
    .\windows-build.ps1 -SkipSidecar      跳过 Sidecar 构建
    .\windows-build.ps1 -ForceSidecar     强制重新构建 Sidecar
    .\windows-build.ps1 -Portable          同时打包绿色版
#>

param(
    [switch]$Clean,
    [switch]$SkipSidecar,
    [switch]$ForceSidecar,
    [switch]$Portable
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Python 镜像源（清华源）
$env:UV_INDEX_URL = "https://pypi.tuna.tsinghua.edu.cn/simple"
$env:UV_EXTRA_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple"

# ============================================================
#  工具函数
# ============================================================

function Write-Step {
    param([string]$Step, [string]$Msg)
    Write-Host ""
    Write-Host "  [$Step] $Msg" -ForegroundColor Cyan
    Write-Host "  $($('-' * 50))" -ForegroundColor DarkGray
}

function Write-OK    { param([string]$Msg) Write-Host "  [OK] $Msg" -ForegroundColor Green }
function Write-Err   { param([string]$Msg) Write-Host "  [ERROR] $Msg" -ForegroundColor Red }
function Write-Warn  { param([string]$Msg) Write-Host "  [WARN] $Msg" -ForegroundColor Yellow }

function Test-Command {
    param([string]$Name)
    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Format-Duration {
    param([TimeSpan]$Duration)
    if ($Duration.TotalMinutes -ge 1) {
        return "{0}m {1:N0}s" -f [math]::Floor($Duration.TotalMinutes), $Duration.Seconds
    }
    return "{0:N1}s" -f $Duration.TotalSeconds
}

function Ask-YesNo {
    param([string]$Prompt, [bool]$Default = $false)
    $suffix = if ($Default) { "[Y/n]" } else { "[y/N]" }
    $answer = Read-Host "  $Prompt $suffix"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $Default }
    return $answer -match '^[yY]'
}

# ============================================================
#  横幅
# ============================================================

Write-Host ""
Write-Host "  ========================================"  -ForegroundColor Yellow
Write-Host "   HanCast 构建脚本 v2.0"                       -ForegroundColor Yellow
Write-Host "  ========================================"  -ForegroundColor Yellow
Write-Host ""

# ============================================================
#  检查是否在项目根目录
# ============================================================

if (-not (Test-Path "package.json") -or -not (Test-Path "src-tauri\Cargo.toml")) {
    Write-Err "请在项目根目录下运行此脚本"
    Write-Host "  用法: .\windows-build.ps1 [-Clean] [-SkipSidecar] [-ForceSidecar]"
    exit 1
}

# ============================================================
#  Step 1: 检查前置依赖
# ============================================================

Write-Step "1" "检查前置依赖..."

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
$pyVerOutput = python --version 2>&1
$pyVerMatch = $pyVerOutput | Select-String -Pattern "(\d+)\.(\d+)\.(\d+)"
if (-not $pyVerMatch) {
    Write-Err "无法获取 Python 版本: $pyVerOutput"
    exit 1
}

$pyMajor = [int]$pyVerMatch.Matches[0].Groups[1].Value
$pyMinor = [int]$pyVerMatch.Matches[0].Groups[2].Value
if ($pyMajor -lt 3 -or ($pyMajor -eq 3 -and $pyMinor -lt 11)) {
    Write-Err "需要 Python 3.11+，当前: $pyVerOutput"
    exit 1
}

Write-OK "全部依赖就绪 ($pyVerOutput)"

# ============================================================
#  Step 2: 初始化 Python 环境
# ============================================================

Write-Step "2" "初始化 Python 环境..."

Push-Location hancast-backend
try {
    uv sync --all-extras
    if ($LASTEXITCODE -ne 0) { throw "uv sync 失败" }
    Write-OK "Python 环境就绪"
} catch {
    Write-Err "Python 环境初始化失败: $_"
    exit 1
} finally {
    Pop-Location
}

# ============================================================
#  交互式选项（无参数时）
# ============================================================

$anyParam = $Clean -or $SkipSidecar -or $ForceSidecar -or $Portable

if (-not $anyParam) {
    Write-Host ""
    Write-Host "  请选择构建选项:" -ForegroundColor Cyan
    Write-Host ""

    $Clean        = Ask-YesNo "是否清理构建产物？"
    $SkipSidecar  = Ask-YesNo "是否跳过 Sidecar 构建？"
    $ForceSidecar = Ask-YesNo "是否强制重建 Sidecar？"
    $Portable     = Ask-YesNo "是否打包绿色版？"

    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │  构建配置                            │" -ForegroundColor DarkGray
    Write-Host "  ├─────────────────────────────────────┤" -ForegroundColor DarkGray

    function Fmt-YN { param([bool]$V) if ($V) { return "✓ 是" } else { return "✗ 否" } }

    Write-Host ("  │  清理构建:      {0}              │" -f (Fmt-YN $Clean))        -ForegroundColor $(if ($Clean) { "Yellow" } else { "DarkGray" })
    Write-Host ("  │  跳过 Sidecar:  {0}              │" -f (Fmt-YN $SkipSidecar))  -ForegroundColor $(if ($SkipSidecar) { "Yellow" } else { "DarkGray" })
    Write-Host ("  │  强制重建:      {0}              │" -f (Fmt-YN $ForceSidecar)) -ForegroundColor $(if ($ForceSidecar) { "Yellow" } else { "DarkGray" })
    Write-Host ("  │  打包绿色版:    {0}              │" -f (Fmt-YN $Portable))     -ForegroundColor $(if ($Portable) { "Yellow" } else { "DarkGray" })

    Write-Host "  └─────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""

    if (-not (Ask-YesNo "确认开始构建？" $true)) {
        Write-Host "  已取消" -ForegroundColor Yellow
        exit 0
    }
} else {
    # 参数模式：显示当前配置
    if ($Clean)        { Write-Host "  模式: 清理构建" -ForegroundColor DarkYellow }
    if ($SkipSidecar)  { Write-Host "  模式: 跳过 Sidecar" -ForegroundColor DarkYellow }
    if ($ForceSidecar) { Write-Host "  模式: 强制重建 Sidecar" -ForegroundColor DarkYellow }
    if ($Portable)     { Write-Host "  模式: 打包绿色版" -ForegroundColor DarkYellow }
    Write-Host ""
}

# 构建计时开始
$buildStart = Get-Date

# ============================================================
#  清理（可选）
# ============================================================

if ($Clean) {
    Write-Host "  [清理] 删除构建产物..." -ForegroundColor DarkYellow
    @(
        "hancast-backend\dist",
        "hancast-backend\build"
    ) | ForEach-Object {
        if (Test-Path $_) {
            Remove-Item $_ -Recurse -Force
            Write-Host "    删除 $_" -ForegroundColor DarkGray
        }
    }
    # 清理 src-tauri/ 下的 Nuitka 输出
    @("*.dll", "*.pyd") | ForEach-Object {
        Get-ChildItem "src-tauri\$_" -ErrorAction SilentlyContinue | ForEach-Object {
            Remove-Item $_ -Force
            Write-Host "    删除 $_" -ForegroundColor DarkGray
        }
    }
    @("hancast_sidecar", "certifi", "lxml", "charset_normalizer", "types") | ForEach-Object {
        $p = "src-tauri\$_"
        if (Test-Path $p) {
            Remove-Item $p -Recurse -Force
            Write-Host "    删除 $p" -ForegroundColor DarkGray
        }
    }
    Get-ChildItem "src-tauri\hancast-sidecar-*.exe" -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-Item $_ -Force
        Write-Host "    删除 $_" -ForegroundColor DarkGray
    }
    # 清理 target\release 但保留 dist-portable
    if (Test-Path "src-tauri\target\release") {
        Get-ChildItem "src-tauri\target\release" -Exclude "dist-portable" | ForEach-Object {
            Remove-Item $_ -Recurse -Force
            Write-Host "    删除 $_" -ForegroundColor DarkGray
        }
    }
    Get-ChildItem "hancast-backend\*.spec" -ErrorAction SilentlyContinue | Remove-Item -Force
    Write-OK "已清理"
}

# ============================================================
#  Step 3: 构建 Nuitka Sidecar
# ============================================================

if (-not $SkipSidecar) {
    # 检查 Nuitka
    $nuitkaInstalled = uv run python -m nuitka --version 2>&1
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "Nuitka 未安装，将在 uv sync 时安装"
    }

    Write-Step "3" "构建 Nuitka Sidecar (standalone)..."
    Write-Host "    首次约 5-15 min，之后走缓存" -ForegroundColor DarkGray
    Write-Host ""

    $sidecarExe = "src-tauri\hancast-sidecar-x86_64-pc-windows-msvc.exe"

    if (-not $ForceSidecar -and (Test-Path $sidecarExe)) {
        $size = (Get-ChildItem "src-tauri\hancast-sidecar-*", "src-tauri\*.dll", "src-tauri\*.pyd", "src-tauri\hancast_sidecar", "src-tauri\certifi", "src-tauri\lxml", "src-tauri\charset_normalizer" -ErrorAction SilentlyContinue -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
        $sizeStr = "{0:N1} MB" -f $size
        Write-OK "Sidecar 已存在，跳过构建"
        Write-Host "    大小: $sizeStr" -ForegroundColor DarkGray
        Write-Host "    使用 -ForceSidecar 强制重新构建" -ForegroundColor DarkGray
    } else {
        $sidecarStart = Get-Date

        Push-Location hancast-backend
        try {
            $buildArgs = @("run", "python", "scripts/build_sidecar.py")
            if ($ForceSidecar) { $buildArgs += "--force" }

            uv @buildArgs
            if ($LASTEXITCODE -ne 0) { throw "Nuitka 构建失败" }
        } catch {
            Write-Err "Sidecar 构建失败: $_"
            exit 1
        } finally {
            Pop-Location
        }

        $sidecarDuration = (Get-Date) - $sidecarStart
        Write-OK "Sidecar 构建完成 ($(Format-Duration $sidecarDuration))"
    }
} else {
    Write-Step "3" "跳过 Nuitka Sidecar 构建"
    Write-Warn "确保 src-tauri\ 下存在 hancast-sidecar 及其依赖文件"
}

# ============================================================
#  Step 4: 前端构建 + Tauri 打包
# ============================================================

Write-Step "4" "前端构建 + Tauri 打包..."
Write-Host "    前端     npm run build"     -ForegroundColor DarkGray
Write-Host "    Tauri    cargo tauri build" -ForegroundColor DarkGray
Write-Host ""

$tauriStart = Get-Date

cargo tauri build
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Err "构建失败，请检查上方输出"
    exit 1
}

$tauriDuration = (Get-Date) - $tauriStart
Write-OK "Tauri 打包完成 ($(Format-Duration $tauriDuration))"

# ============================================================
#  Step 5: 打包绿色版（可选）
# ============================================================

if ($Portable) {
    Write-Step "5" "打包绿色版..."

    $portableDir = "src-tauri\target\release\dist-portable"
    $releaseDir = "src-tauri\target\release"

    # 读取版本号（SSOT: package.json）
    $pkgJson = Get-Content "package.json" -Raw | ConvertFrom-Json
    $appVersion = $pkgJson.version

    # 检查 release 目录
    if (-not (Test-Path "$releaseDir\HanCast.exe")) {
        Write-Err "构建产物未找到: $releaseDir\HanCast.exe"
        exit 1
    }

    # 检查所有需要复制的源文件/目录
    $portableItems = @(
        @{ Src = "$releaseDir\hancast-sidecar.exe"; Type = "文件" },
        @{ Src = "$releaseDir\python312.dll";        Type = "文件" },
        @{ Src = "$releaseDir\mpv";                  Type = "目录" }
    )
    foreach ($item in $portableItems) {
        if (-not (Test-Path $item.Src)) {
            Write-Err "$($item.Type)不存在: $($item.Src)"
            Write-Host "  请确保 Tauri 构建完整，或使用 -SkipSidecar 跳过 Sidecar 构建" -ForegroundColor DarkGray
            exit 1
        }
    }

    # 清理旧目录
    if (Test-Path $portableDir) {
        Remove-Item $portableDir -Recurse -Force
    }

    # 创建目标目录
    New-Item -ItemType Directory -Path $portableDir -Force | Out-Null

    # 复制主程序
    Copy-Item "$releaseDir\HanCast.exe" -Destination "$portableDir\HanCast.exe" -Force

    # 复制 sidecar 可执行文件及依赖（扁平化，全在根目录）
    Copy-Item "$releaseDir\hancast-sidecar.exe" -Destination $portableDir -Force
    Copy-Item "$releaseDir\*.dll" -Destination $portableDir -Force
    Copy-Item "$releaseDir\*.pyd" -Destination $portableDir -Force
    Copy-Item "$releaseDir\certifi" -Destination "$portableDir\certifi" -Recurse -Force
    Copy-Item "$releaseDir\charset_normalizer" -Destination "$portableDir\charset_normalizer" -Recurse -Force
    Copy-Item "$releaseDir\hancast_sidecar" -Destination "$portableDir\hancast_sidecar" -Recurse -Force
    Copy-Item "$releaseDir\lxml" -Destination "$portableDir\lxml" -Recurse -Force

    # 复制 MPV 目录
    Copy-Item "$releaseDir\mpv" -Destination "$portableDir\mpv" -Recurse -Force


    $portableSize = (Get-ChildItem $portableDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    $portableCount = (Get-ChildItem $portableDir -Recurse -File).Count

    $sizeStr = "{0:N1} MB" -f $portableSize
    Write-OK "绿色版打包完成"
    Write-Host "    大小: $sizeStr，文件数: $portableCount" -ForegroundColor DarkGray
} else {
    Write-Step "5" "跳过绿色版打包"
}

# ============================================================
#  完成
# ============================================================

$totalDuration = (Get-Date) - $buildStart

Write-Host ""
Write-Host "  ========================================"  -ForegroundColor Green
Write-Host "   构建完成！"                                   -ForegroundColor Green
Write-Host "  ========================================"  -ForegroundColor Green
Write-Host ""
Write-Host "  耗时: $(Format-Duration $totalDuration)" -ForegroundColor Green
Write-Host ""
Write-Host "  输出:"
$nsisDir = "src-tauri\target\release\bundle\nsis"
if (Test-Path $nsisDir) {
    $nsisExe = Get-ChildItem "$nsisDir\*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($nsisExe) {
        Write-Host "    NSIS 安装包:  $($nsisExe.FullName)" -ForegroundColor Cyan
    } else {
        Write-Host "    NSIS 安装包:  $nsisDir\" -ForegroundColor Cyan
    }
} else {
    Write-Host "    NSIS 安装包:  $nsisDir\ (未找到)" -ForegroundColor DarkGray
}
Write-Host "    绿色版程序:   src-tauri\target\release\HanCast.exe"  -ForegroundColor Cyan
if ($Portable) {
    Write-Host "    绿色版打包:   src-tauri\target\release\dist-portable\" -ForegroundColor Cyan
}
Write-Host ""
