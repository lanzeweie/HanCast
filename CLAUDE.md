# CLAUDE.md — Macast 2.0 项目指南

## 项目概述

**Macast** 是一款跨平台投屏应用，支持将媒体文件/链接投屏到局域网设备，同时可作为 DLNA 接收端。

- **版本**: 2.0（从 1.x 重构）
- **原始代码**: `Macast-main/`（Python 实现，最后更新 2022-01）
- **目标架构**: Tauri 2.0 前端 + Python 后端
- **原作者**: xfangfang
- **协议**: GPL-3.0

## 技术栈

| 层级 | 技术 | 版本要求 |
|------|------|----------|
| 前端框架 | Tauri 2.0 | >= 2.0 |
| 前端 UI | HTML/CSS/JS（Vue 3 + Vite） | Vue 3.3+ |
| 后端服务 | Python | >= 3.11 |
| 桌面特效 | tauri-plugin-vibrancy | 最新 |
| 协议支持 | DLNA/UPnP/SSDP | — |
| 媒体播放 | MPV（外部依赖） | — |

## 项目结构

```
G:\Code\Macast-Han\
├── CLAUDE.md                    # 本文件 — 项目核心约束
├── Macast-main/                 # 原始 1.x Python 源码（参考用）
│   ├── macast/                  # 核心包
│   │   ├── macast.py            # 主逻辑入口
│   │   ├── protocol.py          # DLNA 协议实现
│   │   ├── ssdp.py              # SSDP 设备发现
│   │   ├── renderer.py          # 渲染器基类
│   │   ├── server.py            # HTTP 服务
│   │   ├── gui.py               # 系统托盘 GUI
│   │   ├── utils.py             # 工具函数
│   │   └── xml/                 # UPnP 描述 XML
│   ├── macast_renderer/
│   │   └── mpv.py               # MPV 播放器渲染器
│   └── i18n/                    # 国际化资源
├── docs/                        # 设计文档
│   └── Macast-Functional-Spec.md  # 功能规格说明
├── _bmad/                       # BMad 方法论配置
├── .claude/                     # Claude Code 配置
│   └── memory/                  # 项目记忆与进度追踪
└── src-tauri/                   # [待创建] Tauri Rust 后端
```

## 核心架构约束

### 1. 前端职责边界（关键）
- 前端 **仅负责** UI 展示和用户交互
- **禁止** 在前端实现视频解码或流媒体播放
- 所有媒体处理、协议通信必须通过 Rust/Python 后端
- 原因：避免 WebKit (macOS) vs Chromium (Windows) 的解码兼容性问题

### 2. 跨平台 WebView 兼容性
| 平台 | 引擎 | 注意事项 |
|------|------|----------|
| Windows 10/11 | WebView2 (Chromium) | 支持大部分现代 CSS/JS |
| macOS | WebKit (Safari) | 限制较多，避免最新特性 |
| Linux | WebKitGTK | 功能最少，需严格测试 |

**CSS 兼容规则**:
- 使用 `@supports` 检测特性支持
- 避免 `-webkit-` 前缀依赖
- 使用标准 Flexbox/Grid 布局
- 字体回退链：`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif`

### 3. 系统窗口特效
```rust
// Rust 后端条件编译
#[cfg(target_os = "windows")]  → Mica / Acrylic
#[cfg(target_os = "macos")]    → Vibrancy
#[cfg(target_os = "linux")]    → 无特效，纯色背景
```

### 4. 进程架构
```
┌─────────────────┐     IPC      ┌─────────────────┐
│  Tauri Frontend  │ ←──────────→ │  Rust Backend    │
│  (WebView)       │              │  (Tauri Core)    │
└─────────────────┘              └────────┬────────┘
                                          │ HTTP/IPC
                                          ▼
                                 ┌─────────────────┐
                                 │  Python Backend  │
                                 │  (DLNA/SSDP)     │
                                 └─────────────────┘
```

## 原始代码复用清单

| 文件 | 用途 | 复用策略 |
|------|------|----------|
| `macast/ssdp.py` | SSDP 设备发现 | 直接复用，适配新架构 |
| `macast/protocol.py` | DLNA 协议 | 直接复用，需重构接口 |
| `macast/renderer.py` | 渲染器基类 | 直接复用 |
| `macast_renderer/mpv.py` | MPV 播放器 | 直接复用 |
| `macast/server.py` | HTTP 服务 | 需重写（CherryPy → FastAPI/aiohttp） |
| `macast/gui.py` | 系统托盘 | 废弃，由 Tauri 前端替代 |
| `macast/utils.py` | 工具函数 | 部分复用 |
| `macast/xml/*.xml` | UPnP 描述 | 直接复用 |

## 关键依赖

### Python 后端
```
requests>=2.28.0
lxml>=4.9.0
netifaces>=0.11.0
cherrypy>=18.0.0  # 或迁移到 aiohttp
pydantic>=2.0     # 数据验证
```

### Rust/Tauri
```toml
[dependencies]
tauri = { version = "2", features = ["shell-open"] }
tauri-plugin-vibrancy = "最新"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
```

## 开发工作流

### 构建命令
```bash
# 前端开发
cd src-tauri && cargo tauri dev

# Python 后端
cd macast-backend && python -m uvicorn main:app --reload

# 生产构建
cargo tauri build
```

### 测试策略
- 单元测试：Python pytest + Rust cargo test
- 集成测试：Tauri WebDriver
- 跨平台测试：Windows/macOS/Linux 各一

## 开发阶段

### Phase 1: 基础架构
- [ ] 初始化 Tauri 2.0 项目
- [ ] 配置 Python 后端环境
- [ ] 实现 Rust ↔ Python 通信桥
- [ ] 配置窗口特效

### Phase 2: 前端 UI
- [ ] 自定义标题栏
- [ ] 媒体输入区（拖拽 + 链接）
- [ ] 设备列表区
- [ ] 设置面板

### Phase 3: 后端功能
- [ ] 移植 SSDP 设备发现
- [ ] 移植 DLNA 协议
- [ ] 媒体解析与流服务

### Phase 4: 集成与优化
- [ ] 文件拖拽投屏
- [ ] 链接解析投屏
- [ ] 多设备同步
- [ ] 国际化

## 安全约束

1. **文件拖拽**：验证文件类型和大小，防止恶意文件
2. **URL 解析**：防止 SSRF 攻击，限制可访问范围
3. **本地服务**：仅监听 `127.0.0.1`，不暴露到网络
4. **插件系统**：沙箱化执行，限制文件系统访问

## 代码风格

### Python
- 遵循 PEP 8
- 使用 type hints
- 异步优先（asyncio）
- 日志使用 `logging` 模块

### Rust
- 遵循 `rustfmt` 默认配置
- 使用 `thiserror` 处理错误
- 异步使用 `tokio`

### 前端
- Vue 3 Composition API
- TypeScript 优先
- CSS 变量实现主题切换
- 组件化开发

## 记忆系统

项目进度和关键决策记录在 `.claude/memory/` 目录：
- `progress.md` — 开发进度追踪
- `decisions.md` — 架构决策记录
- `issues.md` — 已知问题与解决方案
- `context.md` — 项目上下文快照

**重要**：每次会话开始时读取 memory 文件，结束时更新进度。
