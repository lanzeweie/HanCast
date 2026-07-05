<p align="center">
  <img src="src-tauri/icons/icon.png" width="120" alt="Macast Logo">
</p>

<h1 align="center">Macast 2.0</h1>

<p align="center">
  跨平台投屏应用 — 将媒体文件/链接投屏到局域网设备，同时可作为 DLNA 接收端
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/macOS-12%2B-black?logo=apple" alt="macOS">
  <img src="https://img.shields.io/badge/Linux-Ubuntu%2020.04%2B-orange?logo=linux" alt="Linux">
  <img src="https://img.shields.io/badge/License-GPL--3.0-green" alt="License">
</p>

---

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
│   │   ├── lib.rs          # Tauri 命令 (16 个)
│   │   └── sidecar.rs      # SidecarManager (Rust ↔ Python)
│   └── Cargo.toml
├── macast-backend/         # Python 后端
│   └── macast_sidecar/
│       ├── main.py         # Sidecar 入口 (stdin/stdout)
│       ├── commands.py     # 命令路由 (16 个命令)
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

# 安装 Python 后端依赖
cd macast-backend
pip install -e .
cd ..
```

### 开发

```bash
# 启动 Tauri 开发模式 (前端 + Rust + Python Sidecar)
npm run tauri dev

# 仅前端开发 (mock 数据，不需要 Python)
npm run dev

# 仅 Python 后端测试
cd macast-backend
python -m macast_sidecar.main
```

### 构建

```bash
# 构建生产版本
npm run tauri build
```

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

## 许可证

[GPL-3.0](LICENSE)

## 致谢

- [xfangfang/Macast](https://github.com/xfangfang/Macast) — 原始 1.x 实现
- [Tauri](https://tauri.app/) — 跨平台桌面应用框架
- [DLNA/UPnP](https://www.dlna.org/) — 局域网投屏协议
