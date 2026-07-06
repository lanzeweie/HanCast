<p align="center">
  <img src="src-tauri/icons/icon.png" width="120" alt="Macast-Han Logo">
</p>

<h1 align="center">Macast-Han</h1>

<p align="center">
  基于 <a href="https://github.com/xfangfang/Macast">Macast</a> 的二次开发 — 跨平台投屏应用
</p>

<p align="center">
  作者: <b>Han</b> &nbsp;|&nbsp; 原项目: <a href="https://github.com/xfangfang/Macast">xfangfang/Macast</a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/macOS-12%2B-black?logo=apple" alt="macOS">
  <img src="https://img.shields.io/badge/Linux-Ubuntu%2020.04%2B-orange?logo=linux" alt="Linux">
  <img src="https://img.shields.io/badge/License-GPL--3.0-green" alt="License">
</p>

---

## 关于

Macast-Han 是对 [xfangfang/Macast](https://github.com/xfangfang/Macast)（最后更新 2022 年）的二次开发。原项目使用 Python + pystray 实现，本项目将其重构为：

- **Tauri 2.0** 替代 pystray 系统托盘（现代化 UI）
- **Rust 壳层** 作为前端与 Python 的桥接
- **Python Sidecar** 复用原项目 DLNA/SSDP 核心代码

**不是原项目的官方更新**，是独立的二次开发作品。

## 功能

- 📱 **接收投屏** — 作为 DLNA Renderer，接收手机/平板的投屏
- 📤 **发送投屏** — 将本地媒体文件投屏到电视/音箱
- 🔗 **链接投屏** — 粘贴媒体链接直接投屏
- 🎮 **播放控制** — 暂停/恢复/跳转/音量调节
- 🔍 **设备发现** — 自动扫描局域网 DLNA 设备
- 🌐 **跨平台** — Windows / macOS / Linux 一致体验

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 前端 | Tauri 2.0 + Vue 3 + TypeScript | WebView UI |
| 桥接 | Rust (Tauri Commands) | 进程管理 + IPC |
| 后端 | Python 3.11+ (Sidecar) | DLNA/SSDP/媒体服务 |
| 播放器 | MPV | 外部依赖 |

## 项目结构

```
Macast-Han/
├── src/                    # 前端 Vue 3 源码
├── src-tauri/              # Rust Tauri 壳层
│   ├── src/
│   │   ├── main.rs         # 入口
│   │   ├── lib.rs          # Tauri 命令 (20 个)
│   │   └── sidecar.rs      # SidecarManager (Rust ↔ Python)
│   └── Cargo.toml
├── macast-backend/         # Python 后端
│   └── macast_sidecar/
│       ├── main.py         # Sidecar 入口 (stdin/stdout)
│       ├── commands.py     # 命令路由 (20 个命令)
│       ├── ssdp.py         # SSDP 设备发现
│       ├── protocol/       # DLNA 协议
│       ├── renderer/       # MPV 渲染器
│       └── media/          # 媒体解析 + HTTP 服务
├── docs/                   # 设计文档
├── Macast-main/            # 原始 1.x 参考代码
└── CLAUDE.md               # 项目指南
```

## 快速开始

### 前置依赖

- [Node.js](https://nodejs.org/) >= 18
- [Rust](https://rustup.rs/) (最新 stable)
- [Python](https://python.org/) >= 3.11
- [MPV](https://mpv.io/) (可选，接收投屏需要)

### 安装

```bash
# 克隆仓库
git clone https://github.com/your-username/Macast-Han.git
cd Macast-Han

# 安装前端依赖
npm install

# 安装 Python 后端依赖 (需要 uv)
cd macast-backend
uv sync
cd ..
```

### 开发

```bash
# 启动 Tauri 开发模式 (前端 + Rust + Python Sidecar 一键启动)
npm run tauri dev

# 仅前端开发 (浏览器 mock 数据，不需要 Python/Rust)
npm run dev

# 仅 Python 后端 (独立调试)
cd macast-backend
uv run python -m macast_sidecar.main
```

### 构建

```bash
# 构建生产版本 (输出到 src-tauri/target/release/bundle/)
npm run tauri build
```

构建产物：
- **MSI 安装包**: `src-tauri/target/release/bundle/msi/Macast-Han_2.0.0_x64_en-US.msi`
- **NSIS 安装包**: `src-tauri/target/release/bundle/nsis/Macast-Han_2.0.0_x64-setup.exe`
- **裸 exe**: `src-tauri/target/release/macast-han.exe`（不推荐直接运行，缺少 Python 环境）

> **注意**: 直接运行 `macast-han.exe` 会闪退，因为它依赖 Python Sidecar（通过 `uv` 启动）。开发测试请用 `npm run tauri dev`。

## 架构

```
┌─────────────────┐     invoke()     ┌─────────────────┐
│  Vue 3 前端      │ ──────────────→ │  Rust Tauri      │
│  (WebView)       │ ←────────────── │  (SidecarManager)│
└─────────────────┘     Promise      └────────┬────────┘
                                              │ stdin/stdout JSON
                                              ▼
                                     ┌─────────────────┐
                                     │  Python Sidecar  │
                                     │  (DLNA/SSDP/MPV) │
                                     └─────────────────┘
```

**通信协议**: 前端通过 Tauri `invoke()` 调用 Rust 命令，Rust 通过 stdin/stdout JSON 与 Python Sidecar 通信。

## 文档

| 文档 | 说明 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 项目指南与约束 |
| [前端设计规格](docs/Macast-Frontend-Spec.md) | UI 组件、样式、路由 |
| [后端设计规格](docs/Macast-Backend-Spec.md) | Rust/Python 架构、通信协议 |
| [前端 API 接口](docs/Macast-Frontend-API.md) | invoke 命令速查 |
| [功能规格](docs/Macast-Functional-Spec.md) | 原始功能设计 |

## 与原项目的关系

| | 原 Macast | Macast-Han |
|---|---|---|
| 作者 | xfangfang | Han |
| 前端 | pystray 系统托盘 | Tauri 2.0 + Vue 3 |
| 后端 | Python (CherryPy) | Python (Sidecar stdin/stdout) |
| 桥接 | 无 | Rust (Tauri Commands) |
| 状态 | 2022 年停更 | 2026 年二次开发 |

**复用的代码**: SSDP 设备发现、DLNA 协议、MPV 渲染器、UPnP XML 描述文件

## 许可证

基于 [GPL-3.0](LICENSE) — 继承原项目协议

## 致谢

- [xfangfang/Macast](https://github.com/xfangfang/Macast) — 原始项目，本项目的基础
- [Tauri](https://tauri.app/) — 跨平台桌面应用框架
- [DLNA/UPnP](https://www.dlna.org/) — 局域网投屏协议
