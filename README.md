<p align="center">
  <img src="src-tauri/icons/icon.png" width="120" alt="HanCast Logo">
</p>

<h1 align="center">HanCast</h1>

<p align="center">
  跨平台投屏应用 — 将媒体投屏到局域网设备，或从手机投屏到电脑
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-10%2F11-blue?logo=windows" alt="Windows">
  <img src="https://img.shields.io/badge/macOS-12%2B-black?logo=apple" alt="macOS">
  <img src="https://img.shields.io/badge/Linux-Ubuntu%2020.04%2B-orange?logo=linux" alt="Linux">
  <img src="https://img.shields.io/badge/License-GPL--3.0-green" alt="License">
</p>

---

## 功能特性

### 发送投屏（Cast Out）

将电脑上的媒体内容投屏到局域网内的 DLNA 设备（电视、音箱、投影仪等）：

- **文件投屏** — 拖拽本地媒体文件到窗口，自动解析并投屏
- **链接投屏** — 粘贴媒体 URL（支持 HTTP/HTTPS 直链），直接投屏
- **剪贴板粘贴** — 从剪贴板粘贴媒体链接，一键投屏
- **播放控制** — 暂停 / 恢复 / 进度跳转 / 音量调节 / 静音
- **多格式支持** — 视频、音频、图片均可投屏

### 接收投屏（Cast In）

电脑作为 DLNA Renderer，接收手机/平板的投屏：

- **DLNA 接收** — 手机端使用支持 DLNA 的 App（如爱奇艺、B站等）投屏到电脑
- **MPV 播放** — 底层使用 MPV 播放器，支持几乎所有媒体格式
- **自动启动** — 接收到投屏请求时自动启动 MPV 播放

### 设备管理

- **自动发现** — 启动后自动扫描局域网 DLNA 设备（SSDP 协议）
- **手动刷新** — 支持手动刷新设备列表
- **设备重命名** — 为设备设置自定义名称（本地保存）
- **默认设备** — 设置默认投屏设备，下次启动自动选中
- **设备移除** — 从列表中移除不需要的设备

### 界面与体验

- **自定义标题栏** — 无边框窗口 + 自定义最小化/关闭按钮
- **亮色/暗色主题** — 跟随系统主题自动切换
- **多语言** — 支持中文 / English
- **系统托盘** — 关闭窗口后最小化到托盘，后台运行

---

## 技术架构

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

| 层级 | 技术 | 职责 |
|------|------|------|
| 前端 | Tauri 2.0 + Vue 3 + TypeScript + Pinia | UI 渲染、用户交互、状态管理 |
| 桥接 | Rust (Tauri Commands) | 进程管理、Sidecar 生命周期、IPC |
| 后端 | Python 3.11+ (Sidecar) | DLNA 协议、SSDP 发现、媒体服务 |
| 播放器 | MPV (外部依赖) | 媒体播放、IPC 控制 |

**进程通信**: 前端通过 Tauri `invoke()` 调用 Rust 命令，Rust 通过 stdin/stdout JSON 与 Python Sidecar 通信。

---

## 快速开始

### 前置依赖

| 依赖 | 版本 | 说明 |
|------|------|------|
| [Node.js](https://nodejs.org/) | >= 18 | 前端构建 |
| [Rust](https://rustup.rs/) | 最新 stable | Tauri 构建 |
| [Python](https://python.org/) | >= 3.11 | 后端运行 |
| [uv](https://docs.astral.sh/uv/) | 最新 | Python 包管理（推荐） |
| [MPV](https://mpv.io/) | 任意 | 接收投屏需要，发送投屏可选 |

### 安装与运行

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/HanCast.git
cd HanCast

# 2. 安装前端依赖
npm install

# 3. 安装 Python 后端依赖
cd macast-backend
uv sync
cd ..

# 4. 启动开发模式（前端 + Rust + Python 一键启动）
npm run tauri dev
```

### 仅前端开发

不需要 Python/Rust 环境，使用浏览器 mock 数据开发 UI：

```bash
npm run dev
# 浏览器访问 http://localhost:1420
```

### 仅 Python 后端调试

独立运行 Python Sidecar，用于调试 DLNA/SSDP 逻辑：

```bash
cd macast-backend
uv run python -m macast_sidecar.main
```

### 生产构建

```bash
npm run tauri build
```

构建产物位于 `src-tauri/target/release/bundle/`：
- **MSI 安装包** — Windows 静默安装
- **NSIS 安装包** — Windows 交互式安装

> **注意**: 直接运行 `hancast.exe` 会闪退，因为它依赖 Python Sidecar。开发测试请用 `npm run tauri dev`。

---

## 项目结构

```
HanCast/
├── src/                        # Vue 3 前端
│   ├── components/             # UI 组件
│   │   ├── TitleBar.vue        # 自定义标题栏
│   │   ├── MediaInput.vue      # 媒体输入（拖拽/链接/粘贴）
│   │   ├── DeviceList.vue      # 设备列表
│   │   ├── DeviceCard.vue      # 设备卡片（投屏/重命名/移除）
│   │   └── CastController.vue  # 投屏控制栏
│   ├── stores/                 # Pinia 状态管理
│   ├── locales/                # 国际化资源
│   └── api/commands.ts         # Tauri invoke 封装
│
├── src-tauri/                  # Rust Tauri 壳层
│   ├── src/
│   │   ├── lib.rs              # 20 个 Tauri 命令定义
│   │   └── sidecar.rs          # SidecarManager（Rust ↔ Python）
│   └── Cargo.toml
│
├── macast-backend/             # Python 后端
│   └── macast_sidecar/
│       ├── main.py             # Sidecar 入口（stdin/stdout JSON 循环）
│       ├── commands.py         # 命令路由（20 个命令）
│       ├── ssdp.py             # SSDP 设备发现
│       ├── protocol/
│       │   ├── dlna.py         # DLNA 协议实现
│       │   └── server.py       # DLNA HTTP 服务
│       ├── renderer/
│       │   └── mpv.py          # MPV 渲染器（IPC 控制）
│       ├── media/
│       │   ├── parser.py       # 媒体文件/URL 解析
│       │   └── server.py       # 本地文件 HTTP 服务
│       └── xml/                # UPnP 描述文件
│
└── docs/                       # 设计文档
```

---

## 开发工具与技能

本项目使用以下 AI 辅助开发工具与方法论：

### BMad Method

[BMad Method](https://github.com/bmadcode/BMad-Method) — 结构化产品开发方法论，覆盖从需求分析到实现的全流程。

| 阶段 | 技能 | 说明 |
|------|------|------|
| 分析 | `bmad-brainstorming` | 头脑风暴，多角度创意发散 |
| 分析 | `bmad-forge-idea` | 想法拷问 — 通过角色扮演压力测试，直到想法成熟或廉价失败 |
| 分析 | `bmad-prfaq` | Working Backwards PRFAQ 挑战，从客户视角验证产品概念 |
| 分析 | `bmad-product-brief` | 产品简报创建与验证 |
| 分析 | `bmad-document-project` | 为 AI 上下文生成项目文档 |
| 规划 | `bmad-prd` | 产品需求文档（PRD）创建、编辑与验证 |
| 规划 | `bmad-ux` | UX 设计规范与模式规划 |
| 方案 | `bmad-architecture` | 技术架构设计 — 不变量的精简脊柱 |
| 方案 | `bmad-create-epics-and-stories` | 需求拆分为 Epic 和用户故事 |
| 实现 | `bmad-dev-story` | 按故事规范执行代码实现 |
| 实现 | `bmad-quick-dev` | 快速实现任意需求、Bug 修复或重构 |
| 实现 | `bmad-code-review` | 对抗性代码审查（盲猎人 + 边界猎人 + 验收审计） |
| 审查 | `bmad-review-adversarial-general` | 愤世嫉俗式审查，产出问题报告 |
| 审查 | `bmad-review-edge-case-hunter` | 边界条件穷举分析 |

### 知识图谱

[Understand Anything](https://github.com/understand-anything/understand-anything) — 自动生成项目代码知识图谱，可视化文件依赖、函数调用、模块层级关系。

```bash
# 生成知识图谱
/understand-anything:understand

# 启动可视化仪表板
/understand-anything:understand-dashboard
```

### Claude Code

[Anthropic Claude Code](https://claude.ai/code) — AI 编程助手，提供代码生成、审查、重构等能力。本项目的所有 AI 辅助开发均通过 Claude Code 进行。

**使用的模型：**

| 模型 | 用途 |
|------|------|
| `mimo-v2.5` | 主力模型 — 全场景开发 |
| `mimo-v2.5-pro` | 备用模型 — 复杂任务、深度推理 |

---

## 设计文档

| 文档 | 说明 |
|------|------|
| [CLAUDE.md](CLAUDE.md) | 项目指南与开发约束 |
| [前端设计规格](docs/Macast-Frontend-Spec.md) | UI 组件、样式、路由设计 |
| [后端设计规格](docs/Macast-Backend-Spec.md) | Rust/Python 架构、通信协议 |
| [前端 API 接口](docs/Macast-Frontend-API.md) | 20 个 invoke 命令速查 |

---

## 许可证

[GPL-3.0](LICENSE) — 基于 [xfangfang/Macast](https://github.com/xfangfang/Macast) 二次开发，继承原项目协议。

---

## 致谢

- [xfangfang/Macast](https://github.com/xfangfang/Macast) — 原始项目
- [Tauri](https://tauri.app/) — 跨平台桌面应用框架
- [akFace/mpv.config](https://github.com/akFace/mpv.config) — MPV 主题皮肤（modernz）
