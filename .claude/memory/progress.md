# Macast-Han 开发进度

## 当前阶段: Phase 2 — macOS 可分发打包

**最后更新**: 2026-11-26

---

## 总体进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 1: macOS 核心功能 | ✅ 已完成 | MPV/SSDP/DLNA/退出清理已跑通 |
| Phase 2: macOS 可分发打包 | ✅ 自用链路完成 | mac-build.sh 产出 signed .app + DMG，ad-hoc |
| 真实设备验收 | ⏳ 待开始 | 手机投 Mac、Mac 投电视（无电视） |
| 正式发版 | ⏳ 待开始 | Developer ID + 公证 + staple；Intel 未构建 |

---

## 2026-11-26 — Phase 2 macOS 打包

### 已完成并验证
- 配置按平台拆分：`tauri.conf.json` 只保留公共项，Windows 专属
  `externalBin`/`*.dll`/`*.pyd`/`mpv/*` 移到 `tauri.windows.conf.json`；
  macOS 配置放 `tauri.macos.conf.json`（数组是整体替换，不合并）
- macOS 资源：
  - Nuitka 整套 `hancast-sidecar/**/*` → `Contents/Resources/hancast-sidecar/`
  - `mpv` 整个目录 → `Contents/Resources/mpv/`，内含完整 `mpv.app`
- `minimumSystemVersion` 14.0（与捆绑 mpv.app 的 `minos` 对齐），
  `infoPlist` 显式指向 `src-tauri/Info.plist`
- `mpv_manager` 增加 macOS 打包布局识别：
  `cwd=Resources/hancast-sidecar` 时向上一层找到 `Resources/mpv/mpv.app`，
  优先 bundled，Homebrew 仅作开发回退
- 新增 `mac-build.sh`：对齐 windows-build.ps1 流程，含
  `--rebuild-sidecar` / `--clean-cache` / `--skip-sidecar` / `--skip-mpv` /
  `--no-dmg` / `--download-mpv`
- 新增 `src-tauri/entitlements/{sidecar,mpv}.entitlements`
  （`com.apple.security.cs.disable-library-validation`，Hardened Runtime 时启用）
- 签名顺序：sidecar 内 `.so/.dylib` → sidecar 主二进制 → mpv.app 内部 → mpv.app 外壳
  → Tauri 签外层 .app（Tauri 不递归 Resources，嵌套签名会保留）

### 验证结果
- `./mac-build.sh --skip-sidecar` 成功产出
  `HanCast.app`（108M）与 `HanCast_2.1.0_aarch64.dmg`（44M）
- DMG 挂载后 `codesign --verify --strict` 通过，mpv.app/sidecar 签名均在
- 打包版 sidecar 空环境启动、SSDP 发现真实设备、exit 清理正常
- `MpvManager.check()` 在打包布局下返回 `source=bundled`，
  路径为 `Resources/mpv/mpv.app/Contents/MacOS/mpv`
- mpv.app 自包含检查通过：仅引用 `@executable_path/lib/*` 与系统库，无 Homebrew 路径

### 已知限制
- 当前下载的第三方 mpv.app（stolendata 0.40.0）Mach-O `minos=14.0`，
  因此 `minimumSystemVersion` 已提到 14.0，macOS 12/13 不再宣称支持。
  脚本会从 tauri.macos.conf.json 读取该值并与 mpv 的 minos 对比告警。
- 仅 aarch64；Intel 需要单独构建。
- ad-hoc 签名本机可用，发给他人仍需手动放行；正式发版需 Developer ID + 公证。

---

## 2026-11-26 — Phase 1 macOS MVP

### 已完成并验证
- MPV 检测：macOS 显式候选（Homebrew / .app），brew 0.42.0 可用
- MPV 配置隔离：`~/Library/Application Support/HanCast/mpv` + `--config-dir`
  - 有 `mpv/portable_config` 时按清单摘要同步；`watch_later` 不覆盖
  - macOS 同步后注释 `glsl-shaders`（Anime4K 等 Metal 兼容性未实测）
- `--hwdec=auto-safe`（macOS），MPV 起播冒烟测试通过
- SSDP：dev 与打包版均能响应 M-SEARCH，LOCATION 指向本机 LAN IP
- 本地网络权限：`Info.plist` + 主 App 启动时发送 M-SEARCH，弹窗归属主 App
  - ad-hoc 签名下 TCC 身份不稳定，换路径/新 bundle ID 可能不弹窗；分发需稳定签名
- 退出：`RunEvent::ExitRequested` 统一清理 sidecar → MPV；`Cmd+Q` 实测无残留
- 托盘：macOS 单色模板图标（44px，`icon_as_template`），菜单可打开
- macOS 打包：`tauri.macos.conf.json`
  - 关闭 externalBin，Nuitka 整套 sidecar 作为资源放进 `Contents/Resources/hancast-sidecar/`
  - `signingIdentity: "-"` 自动 ad-hoc 签名
- 修复打包后问题：嵌入式 Python ASCII 编码（`PYTHONUTF8=1` + 显式 utf-8 解码）、
  Nuitka 下 XML 路径 `protocol/..` ENOENT（`normpath`）

### 未验证 / 待办
- 真实手机投屏到 Mac（DLNA SetAVTransportURI + 设备确认）
- Mac 投电视（本机无 DLNA 电视，未测试）
- 设置页目前没有 MPV 手动路径 UI（后端命令 `check_mpv` / `set_mpv_path` 已存在）
- 托盘图标在菜单栏项过多/刘海屏下可能被系统隐藏（代码侧已确认 status item 创建成功）

### 测试结果
- `cargo check` 通过；`npm run tauri build -- --bundles app` 通过
- Nuitka sidecar 打包后空环境启动、SSDP、退出均正常
- `uv run pytest`：18 passed，3 failed（cast_state/volume/mute 旧断言与现接口不一致，非本次改动）

---

## 历史会话记录

### 2026-07-05 — 首次会话
- 完成项目结构分析
- 确定技术栈：Tauri 2.0 + Python
- 创建项目文档体系
- 原始代码最后更新于 2022-01，需要大量现代化改造

### 2026-07-05 — 前后端拆解
- 将原始功能规格文档拆解为两个独立方案
- **前端方案** (Macast-Frontend-Spec.md):
  - Vue 3 + Vite + TypeScript + Pinia
  - Tauri invoke() 命令层定义
  - 组件规格、样式系统、国际化
  - WebView 兼容性约束
- **后端方案** (Macast-Backend-Spec.md):
  - Rust SidecarManager (stdin/stdout IPC)
  - Python Sidecar 入口 + 命令路由器
  - 原始代码复用映射表 (ssdp/protocol/renderer/mpv)
  - 新增 MediaParser + MediaServer
  - 完整通信协议定义
  - PyInstaller 打包流程
