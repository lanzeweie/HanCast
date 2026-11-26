# Macast-Han 架构决策记录

**最后更新**: 2026-11-26

---

## 决策日志

### DEC-001: 前端框架选择
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 使用 Tauri 2.0 作为前端框架
- **理由**:
  - 跨平台支持（Windows/macOS/Linux）
  - 系统原生 WebView，打包体积小
  - Rust 后端性能优秀
  - 支持系统窗口特效（Mica/Vibrancy）
- **替代方案**: Electron（体积大）、Flutter Desktop（生态不成熟）

### DEC-002: 后端语言保留 Python
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 保留 Python 作为后端服务语言
- **理由**:
  - 原始代码为 Python，可复用
  - DLNA/SSDP 协议库成熟
  - 开发效率高
- **风险**: Python 进程管理需要 Rust 层处理

### DEC-003: 前端不做媒体解码
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 前端仅做 UI，所有媒体处理交给后端
- **理由**:
  - 避免 WebKit vs Chromium 解码兼容性问题
  - macOS WebKit 对某些格式支持有限
  - 统一后端处理逻辑更易维护

### DEC-004: 窗口特效策略
- **日期**: 2026-07-05
- **状态**: ✅ 已决定
- **决策**: 使用 tauri-plugin-vibrancy 实现跨平台特效
- **方案**:
  - Windows: Mica / Acrylic
  - macOS: Vibrancy
  - Linux: 无特效，纯色背景

### DEC-005: Rust ↔ Python 通信方式
- **日期**: 2026-07-05
- **状态**: 🔄 待验证
- **决策倾向**: HTTP REST API
- **理由**:
  - 调试方便
  - Python 生态支持好
  - 可选 WebSocket 用于实时状态推送
- **替代方案**: stdin/stdout IPC、gRPC

---

### DEC-006: macOS sidecar 打包方式（Nuitka 整套作为资源）
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 1）
- **决策**: macOS 关闭 Tauri `externalBin`，把 Nuitka 产物（可执行文件 +
  libpython + hancast_sidecar/xml）整体放进 `Contents/Resources/hancast-sidecar/`，
  Rust 侧从该目录启动。
- **理由**:
  - externalBin 只复制单个可执行文件，Nuitka standalone 依赖会丢失
  - macOS 的 resource_dir 与 MacOS 目录分离，Windows 的“同目录”假设不成立
- **配置**: `src-tauri/tauri.macos.conf.json`

### DEC-007: macOS 本地网络授权由主 App 触发
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 1）
- **决策**: 启动时由 Rust 主进程向 SSDP 多播地址发一条 M-SEARCH，再启动 sidecar。
- **理由**:
  - SSDP 在 Python sidecar 中执行；sidecar 不是 App Bundle，TCC 无法为它弹窗，
    会静默拒绝（sendto 返回 EHOSTUNREACH）
  - 主进程先访问本地网络，授权弹窗归属 HanCast（Info.plist 已带
    NSLocalNetworkUsageDescription）
- **风险**: ad-hoc 签名在换路径/换 bundle ID 后 TCC 身份不稳定，可能不再弹窗；
  正式分发应使用稳定的 Apple Development / Developer ID 签名。

### DEC-008: Tauri 配置按平台拆分
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 2）
- **决策**: `tauri.conf.json` 只保留公共配置；Windows 专属
  `externalBin` / `*.dll` / `*.pyd` / `mpv/*` 移到 `tauri.windows.conf.json`，
  macOS 资源与签名配置放 `tauri.macos.conf.json`。
- **理由**: 平台配置按 JSON Merge Patch 合并，数组整体替换；混在主配置里会让
  macOS 误带 Windows 资源，也会让 Windows 校验不存在的 mac 路径。
- **注意**: 平台文件由 Tauri 自动加载；CLI `--config` 最后合并，可用于正式签名覆盖。

### DEC-009: macOS 整包分发 mpv.app
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 2）
- **决策**: 不拆二进制，整个 `mpv.app` 放 `Contents/Resources/mpv/mpv.app`，
  sidecar 执行 `Contents/MacOS/mpv`。
- **理由**: mpv 依赖 `@executable_path/lib/*.dylib`，只拷主程序会丢失依赖；
  Homebrew 版引用 `/opt/homebrew`，不可分发。
- **校验**: `mac-build.sh` 用 `otool -L` 扫描，出现 Homebrew/本机绝对路径即失败。

### DEC-010: 嵌套签名顺序与 entitlements
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 2）
- **决策**: sidecar 的 `.so/.dylib` → sidecar 主程序 → mpv.app 内部 →
  mpv.app 外壳 → Tauri 外层 .app；Hardened Runtime 时主程序带
  `disable-library-validation`。
- **理由**: ad-hoc 没有 Team ID，开启 Hardened Runtime 后库验证会拒绝加载
  自己签的 dylib。Tauri 签名只覆盖框架/外部二进制/外层 .app，不递归 Resources，
  所以嵌套签名会保留。
- **正式发版**: Developer ID + 公证（Tauri 读 APPLE_* 环境变量自动提交并 staple）。

### DEC-011: macOS 使用原生红绿灯
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 3）
- **决策**: macOS 窗口改用 `decorations: true` + `titleBarStyle: "Overlay"` +
  `hiddenTitle: true`，放弃自绘最小化/关闭按钮；Windows 仍用自绘标题栏。
- **实现**:
  - `tauri.macos.conf.json` 覆盖整段 `app.windows`（平台配置数组整体替换）
  - 前端按 `isMacOS` 隐藏自绘按钮，标题栏左侧留 78px；红/黄为原生行为
  - WKWebView 不支持 `-webkit-app-region`，用 `data-tauri-drag-region="deep"`
  - Tauri v2 的 `start_dragging` 受 ACL 控制，capabilities 必须显式加
    `core:window:allow-start-dragging`（`core:window:default` 不含该项）
  - 绿钮沿用 `set_maximizable(false)` 保持禁用（窗口是紧凑面板，全屏走菜单）
- **注意**: 改窗口尺寸/参数时需同步 `tauri.conf.json` 与
  `tauri.macos.conf.json` 两份 windows 配置。

### DEC-012: macOS 显式应用菜单
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 3）
- **决策**: 在 setup 中显式构建 macOS 应用菜单（关于 / 服务 / 隐藏 / 隐藏其他 /
  显示全部 / 退出 + 编辑 / 显示 / 窗口），替代 Tauri 默认英文菜单。
- **理由**: 默认菜单标签为英文且 About 无项目信息；显式菜单可带版本、
  GPL/仓库 credits，并与托盘菜单语言一致。
- **Cmd+Q**: 预定义 quit → `NSApp terminate` → `RunEvent::ExitRequested`，
  仍走统一 sidecar/MPV 清理状态机。

### DEC-013: 防火墙指引以“设置页 + 启动日志”呈现
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 3）
- **决策**: 不自动修改系统防火墙；启动时调用
  `socketfilterfw --getglobalstate` 记录状态，设置页展示状态、首次投屏
  允许指引和「打开防火墙设置」入口。
- **理由**: `socketfilterfw` 修改需要管理员权限；误操作系统安全设置风险高。
- **范围**: 指引覆盖 SSDP 1900/UDP 与 DLNA 8080/TCP；提示 HanCast 与
  hancast-sidecar 两个可执行文件都可能出现在系统弹窗中。

### DEC-014: 日志导出合并 Rust 与 Python 日志
- **日期**: 2026-11-26
- **状态**: ✅ 已实施（Phase 3）
- **决策**: 导出日志时把 Rust 会话日志（`app_data_dir/logs/hancast.log`）与
  Python sidecar 日志（`HanCast/logs/hancast.log`）合并写入用户选择的文件。
- **理由**: 两者目录不同（Tauri 用 bundle identifier，Python 用产品名），
  只导出 Python 日志会丢掉启动、网络授权、防火墙、自启等诊断信息。

## 待决策事项

### PENDING-001: Python HTTP 框架
- **选项**: CherryPy（原版） vs FastAPI vs aiohttp
- **倾向**: FastAPI（现代、async、类型安全）
- **阻塞因素**: 需评估原 CherryPy 代码迁移难度

### PENDING-002: 前端 UI 框架
- **选项**: 纯 HTML/CSS vs Vue 3 vs React
- **倾向**: Vue 3 + Vite
- **阻塞因素**: 需确认 Tauri 2.0 最佳实践

### PENDING-003: 状态管理方案
- **选项**: Pinia vs Zustand vs 自定义
- **倾向**: Pinia（Vue 官方推荐）
- **阻塞因素**: 取决于前端框架选择

### PENDING-004: 打包与分发策略
- **选项**: PyInstaller 嵌入 vs 独立 Python 进程
- **倾向**: 独立进程 + 自动启动
- **阻塞因素**: 需测试各平台兼容性
