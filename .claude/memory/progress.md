# Macast-Han 开发进度

## 当前阶段: Phase 1 — macOS 核心链路（MVP）

**最后更新**: 2026-11-26

---

## 总体进度

| 阶段 | 状态 | 说明 |
|------|------|------|
| Phase 1: macOS 核心功能 | 🔄 进行中 | MPV/SSDP/DLNA/退出清理已跑通 |
| 真实设备验收 | ⏳ 待开始 | 手机投 Mac、Mac 投电视（无电视） |
| 打包签名 | ⏳ 待开始 | 当前 ad-hoc，分发需稳定签名 |

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
