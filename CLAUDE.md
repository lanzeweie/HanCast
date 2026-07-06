# CLAUDE.md — Macast-Han 项目指南

## 项目概述

**Macast-Han** 是基于 [xfangfang/Macast](https://github.com/xfangfang/Macast) 的二次开发项目，跨平台投屏应用，支持将媒体文件/链接投屏到局域网设备，同时可作为 DLNA 接收端。

- **项目名**: Macast-Han
- **作者**: Han
- **版本**: 2.0.0
- **性质**: 二次开发（非原项目官方更新）
- **原始代码**: `Macast-main/`（原作者 xfangfang，最后更新 2022-01）
- **目标架构**: Tauri 2.0 前端 + Rust 桥接 + Python Sidecar
- **协议**: GPL-3.0（继承原项目）

## 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 前端框架 | Tauri 2.0 | ^2.0.0 |
| 前端 UI | Vue 3 + TypeScript + Vite | Vue ^3.4.0 |
| 状态管理 | Pinia | ^2.1.7 |
| 路由 | vue-router | ^4.2.5 |
| 国际化 | vue-i18n | ^9.9.0 |
| 桥接层 | Rust (Tauri Core) | — |
| 后端服务 | Python Sidecar | >= 3.11 |
| 协议支持 | DLNA/UPnP/SSDP | — |
| 媒体播放 | MPV（外部依赖） | — |

## 项目结构

```
G:\Code\Macast-Han\
├── CLAUDE.md                    # 本文件 — 项目核心约束
├── README.md
├── package.json                 # 前端依赖
├── vite.config.ts               # Vite 配置
├── tsconfig.json                # TypeScript 配置
├── index.html                   # Vite 入口 HTML
├── env.d.ts                     # Vue 类型声明
│
├── src/                         # Vue 3 前端源码
│   ├── main.ts                  # 应用入口（Pinia/Router/i18n 初始化）
│   ├── App.vue                  # 根组件（主题检测、设置加载）
│   ├── api/
│   │   └── commands.ts          # Tauri invoke 封装 + 浏览器 mock
│   ├── components/
│   │   ├── TitleBar.vue         # 自定义标题栏（最小化、关闭、设置）
│   │   ├── MediaInput.vue       # 拖拽 + URL 输入 + 剪贴板粘贴
│   │   ├── CastControl.vue      # 投屏状态栏（播放/暂停/停止指示）
│   │   ├── DeviceList.vue       # 设备列表（含刷新）
│   │   ├── DeviceCard.vue       # 单个设备卡片（投屏、重命名、移除、设默认）
│   │   └── Footer.vue           # "无设备" 提示底栏
│   ├── views/
│   │   ├── HomeView.vue         # 主视图
│   │   └── SettingsView.vue     # 设置页（语言、DLNA 名称、端口、关于）
│   ├── stores/                  # Pinia 状态管理
│   │   ├── cast.ts              # 投屏状态
│   │   ├── device.ts            # 设备列表（30s 自动刷新）
│   │   ├── media.ts             # 媒体输入状态机
│   │   └── settings.ts          # 应用设置
│   ├── types/                   # TypeScript 类型定义
│   │   ├── cast.ts
│   │   ├── device.ts
│   │   ├── media.ts
│   │   ├── settings.ts
│   │   └── index.ts
│   ├── locales/                 # 国际化资源
│   │   ├── zh-CN.json
│   │   └── en-US.json
│   ├── router/
│   │   └── index.ts             # Hash 路由：/ (Home), /settings (Settings)
│   └── styles/
│       ├── variables.css        # CSS 变量（亮色/暗色主题）
│       └── global.css           # 全局样式
│
├── src-tauri/                   # Tauri Rust 后端
│   ├── Cargo.toml               # Rust 依赖
│   ├── tauri.conf.json          # Tauri 配置
│   ├── build.rs                 # tauri_build::build()
│   ├── icons/                   # 应用图标
│   └── src/
│       ├── main.rs              # 入口，调用 macast_han_lib::run()
│       ├── lib.rs               # Tauri 应用设置 + 20 个命令定义
│       └── sidecar.rs           # Python Sidecar 管理器（stdin/stdout JSON）
│
├── macast-backend/              # Python Sidecar 后端
│   ├── pyproject.toml           # Python 项目配置
│   ├── requirements.txt
│   ├── uv.lock
│   ├── macast_sidecar/
│   │   ├── main.py              # Sidecar 入口（stdin/stdout JSON 循环）
│   │   ├── commands.py          # CommandHandler — 命令路由
│   │   ├── ssdp.py              # SSDP 设备发现（~540 行）
│   │   ├── protocol/
│   │   │   ├── dlna.py          # DLNA 协议实现（~840 行）
│   │   │   └── server.py        # DLNA HTTP 服务（描述、SOAP、SUBSCRIBE）
│   │   ├── renderer/
│   │   │   ├── base.py          # 渲染器基类
│   │   │   └── mpv.py           # MPV 渲染器（IPC: named pipe/unix socket）
│   │   ├── media/
│   │   │   ├── parser.py        # 媒体文件/URL 解析器
│   │   │   └── server.py        # 本地文件 HTTP 服务（支持 Range）
│   │   ├── types/
│   │   │   ├── cast.py          # CastState dataclass
│   │   │   ├── device.py        # Device dataclass
│   │   │   └── media.py         # MediaInfo dataclass
│   │   ├── utils/
│   │   │   ├── config.py        # 配置管理（AppData JSON 文件）
│   │   │   └── logger.py        # 日志设置
│   │   └── xml/                 # UPnP 描述 XML
│   │       ├── Description.xml
│   │       ├── AVTransport.xml
│   │       ├── ConnectionManager.xml
│   │       ├── RenderingControl.xml
│   │       ├── SinkProtocolInfo.csv
│   │       └── setting.html
│   ├── scripts/
│   │   ├── build_sidecar.py     # PyInstaller 构建脚本
│   │   └── run_sidecar.py       # 独立 Sidecar 运行器
│   └── tests/
│       ├── test_commands.py
│       └── test_imports.py
│
├── Macast-main/                 # 原始 1.x Python 源码（参考用）
├── Macast-plugins-main/         # 原始 Macast 插件（参考用）
├── mpv/                         # 捆绑的 MPV 二进制文件（Windows, ~120MB）
├── docs/                        # 设计文档
│   ├── Macast-Backend-Spec.md
│   ├── Macast-Frontend-API.md
│   ├── Macast-Frontend-Spec.md
│   └── 原型图.png
├── _bmad/                       # BMad 方法论配置
├── _bmad-output/                # BMad 规划/实现产物
└── .claude/                     # Claude Code 配置
    └── memory/                  # 项目记忆与进度追踪
```

## 核心架构

### 进程通信架构

```
┌─────────────────┐     Tauri invoke()     ┌─────────────────┐
│  Vue 3 Frontend  │ ←────────────────────→ │  Rust Backend    │
│  (WebView)       │                        │  (Tauri Core)    │
└─────────────────┘                        └────────┬────────┘
                                                    │ stdin/stdout JSON
                                                    ▼
                                           ┌─────────────────┐
                                           │  Python Sidecar  │
                                           └────────┬────────┘
                                                    │
                              ┌──────────┬──────────┼──────────┬──────────┐
                              ▼          ▼          ▼          ▼          ▼
                         ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
                         │ SSDP   │ │ DLNA   │ │ DLNA   │ │ Media  │ │ MPV    │
                         │ Service│ │Protocol│ │ Server │ │ Server │ │Renderer│
                         └────────┘ └────────┘ └────────┘ └────────┘ └────────┘
```

### Sidecar JSON 协议

**请求** (Rust → Python stdin):
```json
{"id": <u64>, "cmd": "<command_name>", "params": {<args>}}
```

**响应** (Python stdout → Rust):
```json
{"id": <u64>, "success": true, "data": <any>, "error": null}
```

**事件** (Python stdout → Rust，无 id 字段):
```json
{"event": "<event_name>", "data": <object>}
```

### Tauri 命令列表（20 个）

| 类别 | 命令 | 说明 |
|------|------|------|
| 窗口 | `minimize_window` | 最小化窗口 |
| 窗口 | `close_window` | 隐藏到托盘 |
| 设备 | `get_devices` | 获取设备列表 |
| 设备 | `refresh_devices` | 刷新设备列表 |
| 设备 | `set_default_device` | 设置默认设备 |
| 设备 | `rename_device` | 重命名设备 |
| 设备 | `remove_device` | 移除设备 |
| 媒体 | `parse_media_file` | 解析媒体文件 |
| 媒体 | `parse_media_url` | 解析媒体 URL |
| 投屏 | `start_cast` | 开始投屏 |
| 投屏 | `stop_cast` | 停止投屏 |
| 投屏 | `pause_cast` | 暂停投屏 |
| 投屏 | `resume_cast` | 恢复投屏 |
| 投屏 | `seek_cast` | 跳转进度 |
| 投屏 | `get_cast_state` | 获取投屏状态 |
| 投屏 | `get_cast_url` | 获取当前投屏 URL 和进度 |
| 投屏 | `set_volume` | 设置音量 |
| 投屏 | `set_mute` | 设置静音 |
| 设置 | `get_settings` | 获取设置 |
| 设置 | `save_settings` | 保存设置 |

### Python 后端服务

| 服务 | 端口 | 说明 |
|------|------|------|
| DLNA Server | 8080 | 描述 XML、SCPDXML、SOAP 请求处理 |
| SSDP Service | 1900 | UDP 多播，设备发现（NOTIFY + M-SEARCH） |
| Media Server | 动态 | 本地文件 HTTP 服务（支持 Range 请求） |
| MPV Renderer | IPC | 通过 named pipe (Windows) / unix socket (Linux/macOS) 控制 MPV |

## 原始代码复用情况

| 文件 | 用途 | 状态 |
|------|------|------|
| `macast/ssdp.py` | SSDP 设备发现 | ✅ 已移植到 `macast_sidecar/ssdp.py` |
| `macast/protocol.py` | DLNA 协议 | ✅ 已移植到 `macast_sidecar/protocol/dlna.py` |
| `macast/renderer.py` | 渲染器基类 | ✅ 已移植到 `macast_sidecar/renderer/base.py` |
| `macast_renderer/mpv.py` | MPV 播放器 | ✅ 已移植到 `macast_sidecar/renderer/mpv.py` |
| `macast/server.py` | HTTP 服务 | ✅ 重写为 `protocol/server.py` + `media/server.py`（使用 http.server） |
| `macast/gui.py` | 系统托盘 | ❌ 废弃，由 Tauri 前端替代 |
| `macast/utils.py` | 工具函数 | ✅ 部分复用到 `utils/config.py` + `utils/logger.py` |
| `macast/xml/*.xml` | UPnP 描述 | ✅ 直接复用到 `macast_sidecar/xml/` |

## 依赖

### 前端 (package.json)
```json
{
  "@tauri-apps/api": "^2.0.0",
  "@tauri-apps/plugin-shell": "^2.0.0",
  "pinia": "^2.1.7",
  "vue": "^3.4.0",
  "vue-i18n": "^9.9.0",
  "vue-router": "^4.2.5"
}
```

### Rust (Cargo.toml)
```toml
tauri = { version = "2", features = ["tray-icon"] }
tauri-plugin-shell = "2"
tauri-plugin-clipboard-manager = "2"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["sync", "macros", "rt-multi-thread"] }
```

### Python (pyproject.toml)
```toml
requires-python = ">=3.11"
dependencies = [
    "requests>=2.28.0",
    "lxml>=4.9.0",
    "netifaces>=0.11.0",
]
```

## 开发工作流

### 启动开发环境
```bash
# 启动 Tauri 开发模式（自动启动 Vite 前端 + Python Sidecar）
cargo tauri dev

# 仅前端开发（浏览器模式，使用 mock 数据）
npm run dev

# 仅 Python 后端
cd macast-backend && uv run python -m macast_sidecar.main
```

### 生产构建
```bash
# 构建 Tauri 应用
cargo tauri build

# 构建 Python Sidecar（PyInstaller）
cd macast-backend && python scripts/build_sidecar.py
```

### 测试
```bash
# Python 测试
cd macast-backend && uv run pytest

# 前端测试（待实现）
npm run test
```

## 窗口配置

```json
{
  "width": 420,
  "height": 600,
  "minWidth": 360,
  "minHeight": 480,
  "maxWidth": 800,
  "maxHeight": 900,
  "decorations": false,
  "transparent": true
}
```

**注意**: 窗口特效（vibrancy/blur）尚未实现，当前仅使用透明窗口。

## 跨平台 WebView 兼容性

| 平台 | 引擎 | 注意事项 |
|------|------|----------|
| Windows 10/11 | WebView2 (Chromium) | 支持大部分现代 CSS/JS |
| macOS | WebKit (Safari) | 限制较多，避免最新特性 |
| Linux | WebKitGTK | 功能最少，需严格测试 |

**CSS 兼容规则**:
- 使用标准 Flexbox/Grid 布局
- `-webkit-app-region` 用于标题栏拖拽（Tauri 必需）
- 字体回退链：`-apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif`

## 安全约束

1. **文件拖拽**：验证文件类型和大小，防止恶意文件
2. **URL 解析**：防止 SSRF 攻击，限制可访问范围
3. **本地服务**：仅监听 `127.0.0.1`，不暴露到网络
4. **Sidecar 通信**：stdin/stdout 管道，不暴露网络端口

## 代码风格

### Python
- 遵循 PEP 8
- 使用 type hints
- 日志使用 `logging` 模块
- 使用 `dataclass` 定义数据类型

### Rust
- 遵循 `rustfmt` 默认配置
- 使用 `thiserror` 处理错误
- 异步使用 `tokio`

### 前端
- Vue 3 Composition API + TypeScript
- CSS 变量实现主题切换
- 组件化开发
- Pinia 状态管理

## 开发进度

### Phase 1: 基础架构 ✅
- [x] 初始化 Tauri 2.0 项目
- [x] 配置 Python 后端环境
- [x] 实现 Rust ↔ Python 通信桥（SidecarManager）
- [ ] 配置窗口特效（透明窗口已实现，vibrancy 未实现）

### Phase 2: 前端 UI ✅
- [x] 自定义标题栏
- [x] 媒体输入区（拖拽 + 链接 + 剪贴板）
- [x] 设备列表区
- [x] 设置面板
- [x] 主题切换（亮色/暗色）
- [x] 国际化（zh-CN/en-US）

### Phase 3: 后端功能 ✅
- [x] 移植 SSDP 设备发现
- [x] 移植 DLNA 协议
- [x] 媒体解析与流服务
- [x] MPV 渲染器集成

### Phase 4: 集成与优化 🚧
- [x] 文件拖拽投屏（前端已实现，Tauri 文件路径提取待测试）
- [x] 链接解析投屏
- [ ] 多设备同步（UI 存在但功能禁用）
- [ ] 窗口特效（vibrancy/blur）
- [ ] 完善测试覆盖

## 记忆系统

项目进度和关键决策记录在 `.claude/memory/` 目录：
- `progress.md` — 开发进度追踪
- `decisions.md` — 架构决策记录
- `issues.md` — 已知问题与解决方案
- `context.md` — 项目上下文快照

**重要**：每次会话开始时读取 memory 文件，结束时更新进度。
