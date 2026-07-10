<#
.SYNOPSIS
    HanCast 构建脚本 (Windows)

.DESCRIPTION
    检查依赖 → 初始化 Python → Nuitka 构建 Sidecar → 前端构建 → Tauri 打包
    无参数运行时进入交互式问答，带参数时直接执行（适合 CI/自动化）。

.PARAMETER CleanBuildCache
    清理 Rust 编译缓存 (target/release)

.PARAMETER RebuildSidecar
    重新构建 Python 后端

.PARAMETER Portable
    打包绿色版

.EXAMPLE
    .\windows-build.ps1                       交互式模式
    .\windows-build.ps1 -CleanBuildCache      清理 Rust 缓存后构建
    .\windows-build.ps1 -RebuildSidecar       重新构建 Python 后端
    .\windows-build.ps1 -Portable              打包绿色版
#>

param(
    [switch]$CleanBuildCache,
    [switch]$RebuildSidecar,
    [switch]$Portable
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

# Python 镜像源
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
Write-Host "   HanCast 构建脚本 v3.0"                       -ForegroundColor Yellow
Write-Host "  ========================================"  -ForegroundColor Yellow
Write-Host ""

# ============================================================
#  检查是否在项目根目录
# ============================================================

if (-not (Test-Path "package.json") -or -not (Test-Path "src-tauri\Cargo.toml")) {
    Write-Err "请在项目根目录下运行此脚本"
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

$anyParam = $CleanBuildCache -or $RebuildSidecar -or $Portable

if (-not $anyParam) {
    Write-Host ""
    Write-Host "  请选择构建选项:" -ForegroundColor Cyan
    Write-Host ""

    $CleanBuildCache = Ask-YesNo "清理 Rust 编译缓存 (target/release)？"
    $RebuildSidecar  = Ask-YesNo "重新构建 Python 后端？"
    $Portable        = Ask-YesNo "打包绿色版？"

    Write-Host ""
    Write-Host "  ┌─────────────────────────────────────┐" -ForegroundColor DarkGray
    Write-Host "  │  构建配置                            │" -ForegroundColor DarkGray
    Write-Host "  ├─────────────────────────────────────┤" -ForegroundColor DarkGray

    function Fmt-YN { param([bool]$V) if ($V) { return "✓ 是" } else { return "✗ 否" } }

    Write-Host ("  │  清理 Rust 缓存:  {0}              │" -f (Fmt-YN $CleanBuildCache)) -ForegroundColor $(if ($CleanBuildCache) { "Yellow" } else { "DarkGray" })
    Write-Host ("  │  重建 Python:     {0}              │" -f (Fmt-YN $RebuildSidecar))  -ForegroundColor $(if ($RebuildSidecar) { "Yellow" } else { "DarkGray" })
    Write-Host ("  │  打包绿色版:      {0}              │" -f (Fmt-YN $Portable))         -ForegroundColor $(if ($Portable) { "Yellow" } else { "DarkGray" })

    Write-Host "  └─────────────────────────────────────┘" -ForegroundColor DarkGray
    Write-Host ""

    if (-not (Ask-YesNo "确认开始构建？" $true)) {
        Write-Host "  已取消" -ForegroundColor Yellow
        exit 0
    }
} else {
    # 参数模式
    if ($CleanBuildCache) { Write-Host "  模式: 清理 Rust 缓存" -ForegroundColor DarkYellow }
    if ($RebuildSidecar)  { Write-Host "  模式: 重建 Python 后端" -ForegroundColor DarkYellow }
    if ($Portable)        { Write-Host "  模式: 打包绿色版" -ForegroundColor DarkYellow }
    Write-Host ""
}

# 构建计时开始
$buildStart = Get-Date

# ============================================================
#  Step 3: 清理 Rust 编译缓存（可选）
# ============================================================

if ($CleanBuildCache) {
    Write-Step "3" "清理 Rust 编译缓存..."

    $targetRelease = "src-tauri\target\release"
    if (Test-Path $targetRelease) {
        # 强制终止所有相关进程
        Write-Host "    终止相关进程..." -ForegroundColor DarkGray
        Get-Process | Where-Object {
            $_.Path -and ($_.Path -like "*target\release*" -or $_.Path -like "*dist-portable*")
        } | ForEach-Object {
            Write-Host "    终止: $($_.Name) (PID: $($_.Id))" -ForegroundColor DarkGray
            Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
        }
        @("HanCast", "hancast-sidecar") | ForEach-Object {
            Get-Process -Name $_ -ErrorAction SilentlyContinue | ForEach-Object {
                Write-Host "    终止: $($_.Name) (PID: $($_.Id))" -ForegroundColor DarkGray
                Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue
            }
        }
        Start-Sleep -Seconds 2

        # 清理 target/release（保留 dist-portable）
        $portableDir = "$targetRelease\dist-portable"
        $portableExists = Test-Path $portableDir

        # 使用 cmd 强制删除（绕过文件锁）
        $retries = 5
        for ($i = 0; $i -lt $retries; $i++) {
            try {
                if ($portableExists) {
                    # 先删除 target/release 下除 dist-portable 外的所有内容
                    Get-ChildItem $targetRelease -Exclude "dist-portable" | ForEach-Object {
                        cmd /c "rmdir /s /q `"$($_.FullName)`"" 2>$null
                    }
                } else {
                    cmd /c "rmdir /s /q `"$targetRelease`"" 2>$null
                }
                Write-OK "已清理 $targetRelease"
                break
            } catch {
                if ($i -lt $retries - 1) {
                    Write-Warn "清理失败，重试中... ($($i+1)/$retries)"
                    Start-Sleep -Seconds 2
                } else {
                    Write-Err "无法清理 $targetRelease"
                }
            }
        }
    } else {
        Write-Warn "$targetRelease 不存在，跳过清理"
    }
} else {
    Write-Step "3" "跳过 Rust 缓存清理"
}

# ============================================================
#  Step 4: 构建 Python Sidecar（可选）
# ============================================================

if ($RebuildSidecar) {
    Write-Step "4" "重新构建 Python Sidecar..."

    # 清理旧的 Sidecar 目录
    $sidecarDir = "src-tauri\hancast-sidecar"
    if (Test-Path $sidecarDir) {
        Remove-Item $sidecarDir -Recurse -Force
        Write-Host "    已清理 $sidecarDir" -ForegroundColor DarkGray
    }

    $sidecarStart = Get-Date

    Push-Location hancast-backend
    try {
        uv run python scripts/build_sidecar.py --force
        if ($LASTEXITCODE -ne 0) { throw "Nuitka 构建失败" }
    } catch {
        Write-Err "Sidecar 构建失败: $_"
        exit 1
    } finally {
        Pop-Location
    }

    $sidecarDuration = (Get-Date) - $sidecarStart
    Write-OK "Sidecar 构建完成 ($(Format-Duration $sidecarDuration))"
} else {
    Write-Step "4" "跳过 Sidecar 构建"

    # 检查 Sidecar 是否存在
    $sidecarExe = "src-tauri\hancast-sidecar\hancast-sidecar-x86_64-pc-windows-msvc.exe"
    if (Test-Path $sidecarExe) {
        $size = (Get-ChildItem $sidecarExe -ErrorAction SilentlyContinue).Length / 1MB
        Write-Host "    Sidecar 已存在: $([math]::Round($size, 1)) MB" -ForegroundColor DarkGray
    } else {
        Write-Warn "Sidecar 不存在，建议重新构建"
    }
}

# ============================================================
#  Step 5: 前端构建 + Tauri 打包
# ============================================================

Write-Step "5" "前端构建 + Tauri 打包..."
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
#  Step 6: 打包绿色版（可选）
# ============================================================

if ($Portable) {
    Write-Step "6" "打包绿色版..."

    $portableDir = "src-tauri\target\release\dist-portable"
    $releaseDir = "src-tauri\target\release"
    $sidecarDir = "src-tauri\hancast-sidecar"

    # 读取版本号
    $pkgJson = Get-Content "package.json" -Raw | ConvertFrom-Json
    $appVersion = $pkgJson.version

    # 检查构建产物
    if (-not (Test-Path "$releaseDir\HanCast.exe")) {
        Write-Err "构建产物未找到: $releaseDir\HanCast.exe"
        exit 1
    }

    if (-not (Test-Path "$sidecarDir\hancast-sidecar-x86_64-pc-windows-msvc.exe")) {
        Write-Err "Sidecar 未找到，请先构建 Python 后端"
        exit 1
    }

    # 清理旧目录（带重试）
    if (Test-Path $portableDir) {
        @("HanCast", "hancast-sidecar") | ForEach-Object {
            Get-Process -Name $_ -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
        }
        Start-Sleep -Seconds 1

        $retries = 5
        for ($i = 0; $i -lt $retries; $i++) {
            try {
                cmd /c "rmdir /s /q `"$portableDir`"" 2>$null
                if (-not (Test-Path $portableDir)) { break }
                throw "目录仍然存在"
            } catch {
                if ($i -lt $retries - 1) {
                    Write-Warn "清理失败，重试中... ($($i+1)/$retries)"
                    Start-Sleep -Seconds 2
                } else {
                    Write-Err "无法删除旧目录"
                    exit 1
                }
            }
        }
    }

    # 创建目标目录
    New-Item -ItemType Directory -Path $portableDir -Force | Out-Null

    # 复制主程序
    Copy-Item "$releaseDir\HanCast.exe" -Destination "$portableDir\HanCast.exe" -Force

    # 复制 Sidecar exe（从子目录）
    Copy-Item "$sidecarDir\hancast-sidecar-*.exe" -Destination $portableDir -Force
    # 复制依赖（从 src-tauri 根目录，与 exe 同级）
    $srcTauriRoot = "src-tauri"
    Copy-Item "$srcTauriRoot\*.dll" -Destination $portableDir -Force
    Copy-Item "$srcTauriRoot\*.pyd" -Destination $portableDir -Force
    Copy-Item "$srcTauriRoot\hancast_sidecar" -Destination "$portableDir\hancast_sidecar" -Recurse -Force
    Copy-Item "$srcTauriRoot\certifi" -Destination "$portableDir\certifi" -Recurse -Force
    Copy-Item "$srcTauriRoot\charset_normalizer" -Destination "$portableDir\charset_normalizer" -Recurse -Force
    Copy-Item "$srcTauriRoot\lxml" -Destination "$portableDir\lxml" -Recurse -Force

    # 复制 MPV
    Copy-Item "$releaseDir\mpv" -Destination "$portableDir\mpv" -Recurse -Force

    $portableSize = (Get-ChildItem $portableDir -Recurse | Measure-Object -Property Length -Sum).Sum / 1MB
    $portableCount = (Get-ChildItem $portableDir -Recurse -File).Count

    Write-OK "绿色版打包完成"
    Write-Host "    大小: $([math]::Round($portableSize, 1)) MB，文件数: $portableCount" -ForegroundColor DarkGray
} else {
    Write-Step "6" "跳过绿色版打包"
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
Write-Host "    绿色版程序:   src-tauri\target\release\HanCast.exe"  -ForegroundColor Cyan
if ($Portable) {
    Write-Host "    绿色版打包:   src-tauri\target\release\dist-portable\" -ForegroundColor Cyan
}
Write-Host ""
