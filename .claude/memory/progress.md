# Macast-Han 开发进度

## 当前阶段: Phase 3 — macOS 体验与系统集成

**最后更新**: 2026-11-26

---

## 总体进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 1: macOS 核心功能 | ✅ 已完成 | MPV/SSDP/DLNA/退出清理已跑通 |
| Phase 2: macOS 可分发打包 | ✅ 自用链路完成 | mac-build.sh 产出 signed .app + DMG，ad-hoc |
| Phase 3: macOS 体验与系统集成 | ✅ 已完成（防火墙弹窗待真机） | 原生红绿灯/应用菜单/自启验证/防火墙指引/日志合并 |
| 真实设备验收 | ⏳ 待开始 | 手机投 Mac、Mac 投电视（无电视） |
| 正式发版 | ⏳ 待开始 | Developer ID + 公证 + staple；Intel 未构建 |

---

## 2026-11-26 — Phase 3 macOS 体验与系统集成

### 已完成并验证
- 窗口：macOS 改用原生红绿灯
  - `tauri.macos.conf.json` 覆盖 `app.windows`（数组整体替换）：
    `decorations: true` + `titleBarStyle: "Overlay"` + `hiddenTitle: true`
  - 前端按平台隐藏自绘最小化/关闭，标题栏左侧留 78px 给红绿灯
  - 补 `data-tauri-drag-region="deep"`（WKWebView 不支持
    `-webkit-app-region`）；macOS 上用 `.title-bar--mac` 关掉 CSS app-region，
    避免双路径
  - **关键**：capabilities 增加 `core:window:allow-start-dragging`。
    `core:window:default` 不包含 start_dragging，缺权限时拖拽命令被 ACL
    拒绝且无 UI 提示
  - 绿钮保持禁用（沿用 `set_maximizable(false)`，避免全屏拉伸紧凑布局；
    全屏可走「显示 → 进入全屏幕」）
- 应用菜单：显式构建 macOS 菜单（关于 HanCast / 服务 / 隐藏 / 隐藏其他 /
  显示全部 / 退出 + 编辑 / 显示 / 窗口）；退出走 NSApp terminate →
  `ExitRequested`，复用 sidecar/MPV 清理
- 开机自启：托盘与设置页共用 `apply_autostart`，日志记录结果与
  LaunchAgent 路径 / 是否含 `--minimized`
- 防火墙：启动时读 `socketfilterfw --getglobalstate` 写日志；设置页新增
  「网络」区（状态 / 首次投屏指引 / 打开系统设置）
- 日志导出：合并 Rust 会话日志与 Python sidecar 日志到同一个文件
- 设置页 macOS 文案：关闭提示改为“隐藏到菜单栏”；自启提示先放入
  Applications

### 验证结果（构建 2.1.4，target/release/bundle/macos）
- `--minimized`：SessionLogger 记录启动参数，System Events 窗口数 0
- 应用菜单：菜单栏出现 HanCast / 编辑 / 显示 / 窗口；关于面板可打开；
  「退出 HanCast」与 ⌘Q 均无 sidecar/MPV 残留
- 原生红/黄按钮：红钮隐藏窗口且进程/托盘保留；黄钮最小化
- 标题栏拖动：补 `allow-start-dragging` 后，cliclick 实测窗口位置
  从 (628,259) 变为 (748,329)
- 自启：托盘开启后 `~/Library/LaunchAgents/HanCast.plist` 写入，
  `ProgramArguments` 含 `--minimized`；关闭后 plist 删除
- 防火墙：安装到 /Applications 后系统防火墙为开启（State=1）；
  `socketfilterfw --getappblocked` 显示 HanCast 与 hancast-sidecar 均为
  permitted，8080 正在监听；设置页显示“已开启”，启动日志写入对应提示
- 版本：设置页改为读取 Tauri 应用版本，覆盖安装后显示 2.1.4（不再受旧
  sidecar 常量影响）
- 交付：2.1.4 已覆盖安装到 `/Applications/HanCast.app`；旧 2.1.0 备份在
  `/tmp/HanCast-old-20261126-180823.app`

### 未验证 / 已知限制
- 防火墙“拒绝授权 → 8080 不可达”的故障场景未复现（当前两者均 permitted）
- 真实手机投 Mac 仍受本地网络 TCC 授权影响（测试中出现 SSDP sendto 失败）
- macOS `app.windows` 在平台配置里是整段复制，后续改窗口参数需两边同步

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
