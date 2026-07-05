# Macast 2.0 — 后端设计规格

> **文档版本**: 2.0 (更新)
> **更新日期**: 2026-07-05
> **架构**: Python Sidecar + Tauri 2.0 单一应用
> **不涉及**: 前端 UI 组件、CSS 样式

---

## 1. 架构总览

### 1.1 应用结构

```
┌─────────────────────────────────────────────────────────────────┐
│                     Macast 2.0 单一应用                          │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                 Tauri 主进程 (Rust)                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐               │   │
│  │  │ 窗口管理  │  │ Sidecar  │  │ IPC 桥接  │               │   │
│  │  └──────────┘  └──────────┘  └──────────┘               │   │
│  └─────────────────────────┬────────────────────────────────┘   │
│                            │ stdin/stdout JSON                   │
│  ┌─────────────────────────┴────────────────────────────────┐   │
│  │                Python Sidecar 进程                        │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │ SSDP 发现 │  │ DLNA 协议 │  │ aiohttp  │  │ 命令路由  │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                   WebView 前端                            │   │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐ │   │
│  │  │ 设备列表  │  │ 文件选择  │  │ 投屏控制  │  │ 状态显示  │ │   │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 DLNA 双向角色

Macast 2.0 支持 DLNA 双向通信：

| 角色 | 场景 | 数据流 |
|------|------|--------|
| **渲染器** (接收端) | 手机投屏到本机 | 手机 → DLNA → Macast → MPV 播放 |
| **控制端** (发送端) | 投屏到电视 | 前端 UI → IPC → Macast → DLNA → 电视 |

### 1.3 MPV 职责

MPV **仅用于接收投屏**，不参与本地播放：

- ✅ 手机投屏到本机时，MPV 播放
- ❌ 前端选择文件时，不本地播放，直接投屏到电视

### 1.4 打包结构

```
Macast.app / Macast.exe
├── Macast (Tauri 主进程)
├── macast-sidecar (Python 打包产物)
│   └── 包含所有 Python 依赖
└── resources/
    └── UPnP XML 文件
```

---

## 2. 技术选型

| 组件 | 选择 | 说明 |
|------|------|------|
| 前端框架 | Tauri 2.0 | 轻量、安全、跨平台 |
| 前端 UI | Vue 3 + Vite | 响应式、组件化 |
| 后端语言 | Python 3.11+ | 复用原始代码 |
| HTTP 框架 | aiohttp | 异步支持，替代 CherryPy |
| 进程通信 | stdin/stdout JSON | 零端口占用，自动生命周期管理 |
| 打包工具 | PyInstaller | Python → 单一可执行文件 |
| 播放器 | MPV | 外部依赖，作为渲染器 |

---

## 3. 交互层定义 (三层通信)

### 3.1 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                                                                 │
│   前端 (JS/TS)          Rust 壳层            Python Sidecar     │
│   ─────────────         ─────────            ──────────────     │
│                                                                 │
│   invoke('cmd',args)    Tauri Command        stdin JSON Line    │
│   ─────────────────→    解析参数              ─────────────→    │
│                         转发到 Sidecar                          │
│                                               执行业务逻辑      │
│   Promise<T>            等待响应              stdout JSON Line   │
│   ←─────────────────    反序列化              ←─────────────    │
│                         返回前端                                  │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 通信协议

| 层 | 方向 | 协议 | 格式 | 延迟 |
|----|------|------|------|------|
| 前端 → Rust | 单向调用 | Tauri `invoke()` | JS 参数 → Rust 函数 | <0.1ms |
| Rust → Python | 请求 | stdin JSON Line | `{"id":N,"cmd":"...","params":{...}}` | <1ms |
| Python → Rust | 响应 | stdout JSON Line | `{"id":N,"success":true,"data":...}` | <1ms |

**关键约束**:
- 每条 JSON 必须是单行（`\n` 分隔），不能包含换行符
- 请求必须携带 `id`，响应回传相同 `id` 用于匹配
- Python stderr 用于日志输出，不参与通信

### 3.3 事件推送 (Python → 前端)

除请求-响应模式外，Python 需要主动推送状态变化（如：投屏中断、设备上下线）。

**方案**: Python 定期将状态写入 stdout，Rust 通过 Tauri Event 转发到前端。

```
Python stdout (事件):
{"event":"cast_state_changed","data":{"status":"paused","position":120}}

Rust → 前端:
app.emit("cast_state_changed", payload)

前端监听:
import { listen } from '@tauri-apps/api/event';
listen('cast_state_changed', (event) => { ... });
```

| 事件名 | 触发时机 | 数据 |
|--------|----------|------|
| `cast_state_changed` | 播放/暂停/停止 | `{status, position, volume}` |
| `device_found` | 发现新设备 | `Device` |
| `device_lost` | 设备离线 | `{id}` |
| `cast_error` | 投屏出错 | `{message}` |

### 3.4 完整命令映射表

| 前端 invoke() | Rust Tauri Command | Python Sidecar cmd | 说明 |
|---------------|--------------------|--------------------|------|
| `get_devices()` | `commands::device::get_devices` | `get_devices` | 获取设备列表 |
| `refresh_devices()` | `commands::device::refresh_devices` | `refresh_devices` | 触发扫描 |
| `start_cast(deviceId, mediaUri)` | `commands::cast::start_cast` | `start_cast` | 开始投屏 |
| `stop_cast()` | `commands::cast::stop_cast` | `stop_cast` | 停止投屏 |
| `pause_cast()` | `commands::cast::pause_cast` | `pause_cast` | 暂停投屏 |
| `resume_cast()` | `commands::cast::resume_cast` | `resume_cast` | 恢复投屏 |
| `seek_cast(position)` | `commands::cast::seek_cast` | `seek_cast` | 跳转位置 (HH:MM:SS) |
| `get_cast_state()` | `commands::cast::get_cast_state` | `get_cast_state` | 获取状态 |
| `set_volume(volume)` | `commands::cast::set_volume` | `set_volume` | 音量 |
| `set_mute(muted)` | `commands::cast::set_mute` | `set_mute` | 静音 |
| `parse_media_file(filePath)` | `commands::media::parse_media_file` | `parse_media` | 解析文件 |
| `parse_media_url(url)` | `commands::media::parse_media_url` | `parse_media` | 解析链接 |
| `get_settings()` | `commands::settings::get_settings` | `get_settings` | 获取设置 |
| `save_settings(settings)` | `commands::settings::save_settings` | `save_settings` | 保存设置 |

### 3.5 端到端调用链示例

以 **"用户点击投屏按钮"** 为例，完整数据流：

```
步骤 1 — 前端 (Vue 组件)
──────────────────────────
// DeviceCard.vue
const handleCast = async () => {
  await startCast(device.id, mediaInfo.uri);
  // → 调用 api/commands.ts
}

步骤 2 — 前端 API 层
──────────────────────────
// api/commands.ts
export const startCast = (device_id: string, media_uri: string) =>
  invoke('start_cast', { device_id, media_uri });
  // Tauri 桥接：JS → Rust

步骤 3 — Rust Tauri Command
──────────────────────────
// src-tauri/src/commands/cast.rs
#[tauri::command]
pub async fn start_cast(
    sidecar: State<'_, SidecarManager>,
    device_id: String,
    media_uri: String,
) -> Result<(), String> {
    sidecar.call("start_cast", serde_json::json!({
        "device_id": device_id,
        "media_uri": media_uri
    })).await?;
    Ok(())
}

步骤 4 — Rust SidecarManager
──────────────────────────
// 写入 Python stdin:
{"id":5,"cmd":"start_cast","params":{"device_id":"uuid-xxx","media_uri":"http://192.168.1.5:8080/video.mp4"}}
// 阻塞等待 stdout 响应

步骤 5 — Python CommandHandler
──────────────────────────
// macast_sidecar/commands.py
def _start_cast(self, params):
    device_id = params["device_id"]
    media_uri = params["media_uri"]

    # 如果是本地文件，启动 HTTP 服务
    if not media_uri.startswith("http"):
        media_uri = self.media_server.serve_file(media_uri)

    # 发送 DLNA 指令到目标设备
    self.protocol.set_device(device)
    self.protocol.play(media_uri)

步骤 6 — Python DLNA 协议
──────────────────────────
// 向目标设备发送 SOAP 请求
POST http://192.168.1.100:8080/AVTransport/control
SOAPAction: "urn:schemas-upnp-org:service:AVTransport:1#Play"

步骤 7 — Python stdout 响应
──────────────────────────
{"id":5,"success":true,"data":null}

步骤 8 — Rust 返回前端
──────────────────────────
// SidecarManager 收到响应，解析 id=5 匹配
// 返回 Result::Ok(()) 给 Tauri Command
// Tauri 序列化为 JS Promise resolve

步骤 9 — 前端 UI 更新
──────────────────────────
// DeviceCard.vue
// invoke Promise resolve → 投屏成功，更新状态
```

### 3.6 错误处理流程

```
Python 抛出异常
    ↓
stdout: {"id":5,"success":false,"error":"Device not found"}
    ↓
Rust SidecarManager: 检测 success=false
    ↓
Rust Tauri Command: return Err("Device not found")
    ↓
前端: invoke() Promise reject
    ↓
Vue 组件: catch → 显示错误提示
```

---

## 4. Python Sidecar 设计

### 4.1 项目结构

```
macast-backend/
├── pyproject.toml              # 项目配置
├── requirements.txt
├── macast_sidecar/
│   ├── __init__.py
│   ├── main.py                 # Sidecar 入口 (stdin/stdout)
│   ├── commands.py             # 命令路由与处理器
│   ├── ssdp.py                 # SSDP 设备发现 ← 复用自 Macast-main
│   ├── protocol/
│   │   ├── __init__.py
│   │   ├── dlna.py             # DLNA 协议 ← 复用自 protocol.py
│   │   └── handler.py          # HTTP 处理器 ← 重写自 DLNAHandler
│   ├── renderer/
│   │   ├── __init__.py
│   │   ├── base.py             # 渲染器基类 ← 复用自 renderer.py
│   │   └── mpv.py              # MPV 渲染器 ← 复用自 macast_renderer/mpv.py
│   ├── media/
│   │   ├── __init__.py
│   │   ├── parser.py           # 媒体解析 (新增)
│   │   └── server.py           # HTTP 媒体服务 (新增)
│   ├── types/
│   │   ├── __init__.py
│   │   ├── device.py           # 设备数据结构
│   │   ├── media.py            # 媒体数据结构
│   │   └── cast.py             # 投屏状态
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理 ← 重构自 utils.py
│   │   └── logger.py           # 日志管理
│   └── xml/                    # UPnP 描述文件 ← 直接复用
│       ├── Description.xml
│       ├── AVTransport.xml
│       ├── ConnectionManager.xml
│       ├── RenderingControl.xml
│       └── SinkProtocolInfo.csv
└── scripts/
    └── build_sidecar.py        # PyInstaller 打包脚本
```

### 4.2 原始代码复用映射

| 原始文件 (Macast-main/) | 新位置 | 复用策略 | 改动量 |
|--------------------------|--------|----------|--------|
| `macast/ssdp.py` | `macast_sidecar/ssdp.py` | 直接复用 | 小：移除 cherrypy，改用回调 |
| `macast/protocol.py` DLNAProtocol | `macast_sidecar/protocol/dlna.py` | 直接复用 | 小：移除 CherryPy 依赖 |
| `macast/protocol.py` DLNAHandler | `macast_sidecar/protocol/handler.py` | 重写 | 大：CherryPy → aiohttp |
| `macast/renderer.py` | `macast_sidecar/renderer/base.py` | 直接复用 | 小：移除 cherrypy.engine |
| `macast_renderer/mpv.py` | `macast_sidecar/renderer/mpv.py` | 直接复用 | 小：移除 GUI 回调 |
| `macast/server.py` | `macast_sidecar/server.py` | 重写 | 大：CherryPy → aiohttp |
| `macast/utils.py` | `macast_sidecar/utils/config.py` | 部分复用 | 中：移除 cherrypy 依赖 |
| `macast/gui.py` | — | **废弃** | 由 Tauri 前端替代 |
| `macast/macast.py` Macast(App) | — | **废弃** | 由 Tauri 前端替代 |
| `macast/macast.py` MacastPluginManager | — | **废弃** | 移除插件系统 |
| `macast/xml/*.xml` | `macast_sidecar/xml/` | 直接复用 | 无改动 |

### 4.3 Sidecar 入口

```python
# macast_sidecar/main.py
"""
Tauri Sidecar 入口 - 通过 stdin/stdout JSON 与 Rust 通信

协议格式:
  请求: {"id": <int>, "cmd": <string>, "params": <object>}
  响应: {"id": <int>, "success": <bool>, "data": <any>, "error": <string>}
  事件: {"event": <string>, "data": <object>}
"""

import sys
import json
import asyncio
import logging
import signal
from .commands import CommandHandler

logger = logging.getLogger("macast.sidecar")


def main():
    """Sidecar 主循环"""
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(name)s %(levelname)s: %(message)s"
    )

    handler = CommandHandler()

    # 优雅退出
    def shutdown(signum, frame):
        handler.cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    logger.info("Macast Sidecar started")

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue

        req_id = None
        try:
            request = json.loads(line)
            req_id = request.get("id")
            cmd = request.get("cmd")
            params = request.get("params", {})

            # 特殊命令：退出
            if cmd == "exit":
                handler.cleanup()
                break

            # 执行命令
            result = handler.execute(cmd, params)

            response = {
                "id": req_id,
                "success": True,
                "data": result
            }

        except json.JSONDecodeError as e:
            response = {
                "id": req_id,
                "success": False,
                "error": f"Invalid JSON: {e}"
            }
        except KeyError as e:
            response = {
                "id": req_id,
                "success": False,
                "error": f"Missing field: {e}"
            }
        except Exception as e:
            logger.exception(f"Command error: {e}")
            response = {
                "id": req_id,
                "success": False,
                "error": str(e)
            }

        print(json.dumps(response, ensure_ascii=False), flush=True)

    logger.info("Macast Sidecar exited")


if __name__ == "__main__":
    main()
```

### 4.4 命令路由器

```python
# macast_sidecar/commands.py
"""
命令路由 - 将 Sidecar 命令分发到对应模块
"""

import logging
from typing import Any, Dict
from .ssdp import SSDPService
from .protocol.dlna import DLNAProtocol
from .renderer.mpv import MPVRenderer
from .media.parser import MediaParser
from .media.server import MediaServer
from .types.device import Device
from .types.media import MediaInfo
from .types.cast import CastState
from .utils.config import Config

logger = logging.getLogger("macast.commands")


class CommandHandler:
    def __init__(self):
        self.config = Config()
        self.ssdp = SSDPService()
        self.protocol = DLNAProtocol()
        self.renderer = MPVRenderer()
        self.media_parser = MediaParser()
        self.media_server = MediaServer()
        self.cast_state = CastState()

        # 注册命令
        self._commands: Dict[str, callable] = {
            # 设备管理
            "get_devices": self._get_devices,
            "refresh_devices": self._refresh_devices,
            "set_default_device": self._set_default_device,
            "rename_device": self._rename_device,
            "remove_device": self._remove_device,

            # 投屏控制
            "start_cast": self._start_cast,
            "stop_cast": self._stop_cast,
            "get_cast_state": self._get_cast_state,
            "set_volume": self._set_volume,
            "set_mute": self._set_mute,
            "pause_cast": self._pause_cast,
            "resume_cast": self._resume_cast,
            "seek_cast": self._seek_cast,

            # 媒体解析
            "parse_media": self._parse_media,

            # 设置
            "get_settings": self._get_settings,
            "save_settings": self._save_settings,
        }

        # 启动后台服务
        self._start_services()

    def _start_services(self):
        """启动 SSDP 和媒体服务器"""
        self.ssdp.start()
        self.media_server.start(port=self.config.media_port)

    def execute(self, cmd: str, params: Dict[str, Any]) -> Any:
        """执行命令"""
        if cmd not in self._commands:
            raise ValueError(f"Unknown command: {cmd}")
        return self._commands[cmd](params)

    def cleanup(self):
        """清理资源"""
        self.ssdp.stop()
        self.media_server.stop()
        self.renderer.stop()
        self.protocol.stop()

    # ── 设备管理 ──

    def _get_devices(self, params: dict) -> list:
        devices = self.ssdp.get_devices()
        return [d.to_dict() for d in devices]

    def _refresh_devices(self, params: dict) -> list:
        self.ssdp.scan()
        return self._get_devices(params)

    def _set_default_device(self, params: dict) -> None:
        device_id = params["id"]
        self.config.set_default_device(device_id)
        self.config.save()

    def _rename_device(self, params: dict) -> None:
        device_id = params["id"]
        name = params["name"]
        self.ssdp.rename_device(device_id, name)

    def _remove_device(self, params: dict) -> None:
        device_id = params["id"]
        self.ssdp.remove_device(device_id)

    # ── 投屏控制 ──

    def _start_cast(self, params: dict) -> None:
        device_id = params["device_id"]
        media_uri = params["media_uri"]

        # 如果是本地文件，通过媒体服务器提供 HTTP 访问
        if not media_uri.startswith("http"):
            media_uri = self.media_server.serve_file(media_uri)

        device = self.ssdp.get_device(device_id)
        self.protocol.set_device(device)
        self.protocol.play(media_uri)

        self.cast_state.status = "playing"
        self.cast_state.device_id = device_id

    def _stop_cast(self, params: dict) -> None:
        self.protocol.stop()
        self.cast_state.status = "idle"
        self.cast_state.device_id = None

    def _pause_cast(self, params: dict) -> None:
        self.protocol.pause()
        self.cast_state.status = "paused"

    def _resume_cast(self, params: dict) -> None:
        self.protocol.play()
        self.cast_state.status = "playing"

    def _seek_cast(self, params: dict) -> None:
        position = params["position"]  # HH:MM:SS 格式
        self.protocol.seek(position)

    def _get_cast_state(self, params: dict) -> dict:
        return self.cast_state.to_dict()

    def _set_volume(self, params: dict) -> None:
        volume = params["volume"]
        self.renderer.set_volume(volume)
        self.cast_state.volume = volume

    def _set_mute(self, params: dict) -> None:
        muted = params["muted"]
        self.renderer.set_mute(muted)
        self.cast_state.is_muted = muted

    # ── 媒体解析 ──

    def _parse_media(self, params: dict) -> dict:
        media_type = params["type"]
        if media_type == "file":
            info = self.media_parser.parse_file(params["path"])
        else:
            info = self.media_parser.parse_url(params["url"])
        return info.to_dict()

    # ── 设置 ──

    def _get_settings(self, params: dict) -> dict:
        return self.config.to_dict()

    def _save_settings(self, params: dict) -> None:
        settings = params["settings"]
        self.config.update(settings)
        self.config.save()
```

#### AppSettings 数据结构

```python
# macast_sidecar/utils/config.py
from dataclasses import dataclass, field, asdict
from typing import Optional, Any, Dict

@dataclass
class AppSettings:
    """应用设置 - 对应前端 AppSettings 接口"""
    usn: str = ""                           # 设备唯一标识
    friendly_name: str = "Macast"           # DLNA 广播名
    version: str = "2.0.0"                  # 版本号
    media_port: int = 8080                  # 媒体服务端口
    default_device: Optional[str] = None    # 默认设备 ID
    settings: Dict[str, Any] = field(default_factory=lambda: {
        "language": "zh-CN",
        "notification": True,
        "auto_accept": False,
        "proxy": None,
    })

    def to_dict(self) -> dict:
        return asdict(self)

    def update(self, data: dict):
        """部分更新"""
        for key, value in data.items():
            if hasattr(self, key):
                setattr(self, key, value)
```

---

## 5. aiohttp 服务设计 (替代 CherryPy)

### 5.1 HTTP 服务结构

```python
# macast_sidecar/server.py
"""
aiohttp HTTP 服务 - 替代 CherryPy

功能:
- DLNA 描述文件服务
- DLNA SOAP 控制接口
- DLNA 事件订阅
- 媒体文件 HTTP 服务
"""

import asyncio
import logging
from aiohttp import web

logger = logging.getLogger("macast.server")


class MacastServer:
    def __init__(self, protocol, host="0.0.0.0", port=0):
        self.protocol = protocol
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner = None
        self._setup_routes()

    def _setup_routes(self):
        """设置路由"""
        # DLNA 描述文件
        self.app.router.add_get('/description.xml', self.handle_description)

        # DLNA SOAP 控制
        self.app.router.add_post('/{service}/control', self.handle_control)

        # DLNA 事件订阅
        self.app.router.add_post('/{service}/event', self.handle_subscribe)
        self.app.router.add('/{service}/event', self.handle_subscribe,
                          methods=['SUBSCRIBE', 'UNSUBSCRIBE'])

        # 媒体文件服务
        self.app.router.add_get('/media/{file_id}', self.handle_media)

        # 设置页面 (可选)
        self.app.router.add_get('/', self.handle_index)

    async def start(self):
        """启动服务"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()

        # 获取实际端口
        for socket in site._server.sockets:
            self.port = socket.getsockname()[1]
            break

        logger.info(f"HTTP server started on {self.host}:{self.port}")

    async def stop(self):
        """停止服务"""
        if self.runner:
            await self.runner.cleanup()

    async def handle_description(self, request):
        """返回 DLNA 描述文件"""
        xml = self.protocol.get_description()
        return web.Response(text=xml, content_type='text/xml')

    async def handle_control(self, request):
        """处理 DLNA SOAP 控制请求"""
        service = request.match_info['service']
        body = await request.read()
        response = self.protocol.handle_action(service, body)
        return web.Response(
            body=response,
            content_type='text/xml',
            headers={'EXT': ''}
        )

    async def handle_subscribe(self, request):
        """处理 DLNA 事件订阅"""
        service = request.match_info['service']

        if request.method == 'SUBSCRIBE':
            callback = request.headers.get('CALLBACK')
            timeout = request.headers.get('TIMEOUT', 'Second-1800')
            sid = self.protocol.subscribe(service, callback, timeout)
            return web.Response(
                headers={
                    'SID': sid,
                    'TIMEOUT': timeout
                }
            )
        elif request.method == 'UNSUBSCRIBE':
            sid = request.headers.get('SID')
            self.protocol.unsubscribe(sid)
            return web.Response()
        else:
            # Renew
            sid = request.headers.get('SID')
            timeout = request.headers.get('TIMEOUT', 'Second-1800')
            self.protocol.renew_subscribe(sid, timeout)
            return web.Response(
                headers={'SID': sid, 'TIMEOUT': timeout}
            )

    async def handle_media(self, request):
        """提供媒体文件下载"""
        file_id = request.match_info['file_id']
        file_path, file_size, mime_type = self.media_server.get_file(file_id)

        if not file_path:
            raise web.HTTPNotFound()

        # 处理 Range 请求
        range_header = request.headers.get('Range')
        if range_header:
            start, end = self._parse_range(range_header, file_size)
            return web.Response(
                status=206,
                body=self._read_file_range(file_path, start, end),
                content_type=mime_type,
                headers={
                    'Content-Range': f'bytes {start}-{end}/{file_size}',
                    'Content-Length': str(end - start + 1),
                    'Accept-Ranges': 'bytes'
                }
            )
        else:
            return web.Response(
                body=self._read_file(file_path),
                content_type=mime_type,
                headers={
                    'Content-Length': str(file_size),
                    'Accept-Ranges': 'bytes'
                }
            )

    async def handle_index(self, request):
        """设置页面 (可选)"""
        return web.Response(text="Macast 2.0", content_type='text/html')

    def _parse_range(self, header, file_size):
        """解析 Range 头"""
        range_spec = header.replace("bytes=", "").strip()
        if range_spec.startswith("-"):
            start = file_size - int(range_spec[1:])
            end = file_size - 1
        elif range_spec.endswith("-"):
            start = int(range_spec[:-1])
            end = file_size - 1
        else:
            start, end = range_spec.split("-")
            start, end = int(start), int(end)
        return start, end

    def _read_file(self, path):
        """读取整个文件"""
        with open(path, 'rb') as f:
            return f.read()

    def _read_file_range(self, path, start, end):
        """读取文件的指定范围"""
        with open(path, 'rb') as f:
            f.seek(start)
            return f.read(end - start + 1)
```

### 5.2 DLNA 协议适配

```python
# macast_sidecar/protocol/dlna.py
"""
DLNA 协议 - 复用自 Macast-main/macast/protocol.py

改动点:
- 移除 CherryPy 依赖
- 提取为独立类
- 添加异步支持
- 集成 aiohttp 服务
"""

import logging
from lxml import etree
from typing import Optional, Dict, List
from ..types.device import Device

logger = logging.getLogger("macast.dlna")

NS_AVTRANSPORT = "urn:schemas-upnp-org:service:AVTransport:1"
NS_RENDERING = "urn:schemas-upnp-org:service:RenderingControl:1"
NS_CONNECTION = "urn:schemas-upnp-org:service:ConnectionManager:1"


class DLNAProtocol:
    def __init__(self):
        self._device: Optional[Device] = None
        self._control_url: Optional[str] = None
        self._state: Dict[str, any] = {}
        self._subscribers: Dict[str, any] = {}
        self._init_state()

    def _init_state(self):
        """初始化状态"""
        self._state = {
            'TransportState': 'STOPPED',
            'TransportStatus': 'OK',
            'CurrentMediaDuration': '00:00:00',
            'CurrentTrackDuration': '00:00:00',
            'RelativeTimePosition': '00:00:00',
            'AbsoluteTimePosition': '00:00:00',
            'Volume': 80,
            'Mute': False,
            'CurrentTrackURI': '',
            'CurrentTrackMetaData': '',
        }

    def set_device(self, device: Device):
        """设置目标设备（用于控制端模式）"""
        self._device = device
        self._resolve_control_url()

    def play(self, media_uri: str = None, metadata: str = ""):
        """播放媒体"""
        if media_uri:
            # 设置 URI
            self._send_action(
                NS_AVTRANSPORT, "SetAVTransportURI",
                {
                    "InstanceID": 0,
                    "CurrentURI": media_uri,
                    "CurrentURIMetaData": metadata,
                }
            )
            self._state['CurrentTrackURI'] = media_uri

        # 发送 Play
        self._send_action(
            NS_AVTRANSPORT, "Play",
            {"InstanceID": 0, "Speed": 1}
        )
        self._state['TransportState'] = 'PLAYING'

    def stop(self):
        """停止播放"""
        if self._device:
            self._send_action(
                NS_AVTRANSPORT, "Stop",
                {"InstanceID": 0}
            )
        self._state['TransportState'] = 'STOPPED'

    def pause(self):
        """暂停播放"""
        if self._device:
            self._send_action(
                NS_AVTRANSPORT, "Pause",
                {"InstanceID": 0}
            )
        self._state['TransportState'] = 'PAUSED_PLAYBACK'

    def seek(self, position: str):
        """跳转到指定位置 (HH:MM:SS)"""
        if self._device:
            self._send_action(
                NS_AVTRANSPORT, "Seek",
                {
                    "InstanceID": 0,
                    "Unit": "REL_TIME",
                    "Target": position,
                }
            )
        self._state['RelativeTimePosition'] = position
        self._state['AbsoluteTimePosition'] = position

    def set_volume(self, volume: int):
        """设置音量 (0-100)"""
        if self._device:
            self._send_action(
                NS_RENDERING, "SetVolume",
                {
                    "InstanceID": 0,
                    "Channel": "Master",
                    "DesiredVolume": volume,
                }
            )
        self._state['Volume'] = volume

    def set_mute(self, muted: bool):
        """设置静音"""
        if self._device:
            self._send_action(
                NS_RENDERING, "SetMute",
                {
                    "InstanceID": 0,
                    "Channel": "Master",
                    "DesiredMute": 1 if muted else 0,
                }
            )
        self._state['Mute'] = muted

    def get_description(self) -> str:
        """获取 DLNA 描述 XML"""
        # 从 xml/Description.xml 加载并格式化
        pass

    def handle_action(self, service: str, body: bytes) -> bytes:
        """处理 SOAP 动作请求（用于渲染器模式）"""
        root = etree.fromstring(body)[0][0]
        action = root.tag.split('}')[1]

        # 提取参数
        params = {}
        for node in root:
            params[node.tag] = node.text

        # 处理动作
        handler_name = f"{service}_{action}"
        if hasattr(self, handler_name):
            result = getattr(self, handler_name)(params)
        else:
            result = self._get_default_response(service, action)

        # 构建响应 XML
        return self._build_soap_response(service, action, result)

    def subscribe(self, service: str, callback: str, timeout: str) -> str:
        """订阅事件"""
        import uuid
        sid = f"uuid:{uuid.uuid4()}"
        self._subscribers[sid] = {
            'service': service,
            'callback': callback,
            'timeout': timeout,
        }
        return sid

    def unsubscribe(self, sid: str):
        """取消订阅"""
        self._subscribers.pop(sid, None)

    def renew_subscribe(self, sid: str, timeout: str):
        """续订"""
        if sid in self._subscribers:
            self._subscribers[sid]['timeout'] = timeout

    def _resolve_control_url(self):
        """解析设备的控制 URL"""
        # 从设备描述 XML 中提取服务控制 URL
        pass

    def _send_action(self, service: str, action: str, params: dict):
        """发送 SOAP 请求"""
        # 构建 SOAP XML
        envelope = etree.Element(
            "{http://schemas.xmlsoap.org/soap/envelope/}Envelope"
        )
        body = etree.SubElement(
            envelope,
            "{http://schemas.xmlsoap.org/soap/envelope/}Body"
        )
        action_elem = etree.SubElement(
            body,
            f"{{{service}}}{action}"
        )

        for key, value in params.items():
            child = etree.SubElement(action_elem, key)
            child.text = str(value)

        xml_data = etree.tostring(envelope, xml_declaration=True, encoding="utf-8")

        headers = {
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPAction": f'"{service}#{action}"',
        }

        import requests
        response = requests.post(
            self._control_url,
            data=xml_data,
            headers=headers,
            timeout=10,
        )
        response.raise_for_status()

        return etree.fromstring(response.content)

    def _build_soap_response(self, service: str, action: str, result: dict) -> bytes:
        """构建 SOAP 响应"""
        ns = 'http://schemas.xmlsoap.org/soap/envelope/'
        root = etree.Element(etree.QName(ns, 'Envelope'))
        body = etree.SubElement(root, etree.QName(ns, 'Body'))

        response = etree.SubElement(
            body,
            etree.QName(service, f'{action}Response')
        )

        for key, value in result.items():
            prop = etree.SubElement(response, key)
            prop.text = str(value)

        return etree.tostring(root, encoding="UTF-8", xml_declaration=False)
```

---

## 6. Rust 壳层设计

### 6.1 项目结构

```
src-tauri/
├── Cargo.toml
├── tauri.conf.json
├── build.rs
├── icons/
├── src/
│   ├── main.rs                # 入口
│   ├── lib.rs                 # 库文件
│   ├── commands/
│   │   ├── mod.rs
│   │   ├── device.rs          # 设备管理命令
│   │   ├── cast.rs            # 投屏控制命令
│   │   ├── media.rs           # 媒体解析命令
│   │   └── settings.rs        # 设置管理命令
│   ├── sidecar/
│   │   ├── mod.rs
│   │   ├── manager.rs         # Sidecar 进程管理器
│   │   └── protocol.rs        # JSON 协议定义
│   └── window/
│       ├── mod.rs
│       └── effect.rs          # 窗口特效
└── sidecars/                  # Python 打包产物
    ├── macast-sidecar.exe     # Windows
    └── macast-sidecar         # macOS/Linux
```

### 6.2 Cargo 依赖

```toml
[dependencies]
tauri = { version = "2", features = ["shell-sidecar"] }
tauri-plugin-shell = "2"
tauri-plugin-vibrancy = "0.4"
tauri-plugin-mica = "0.1"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
thiserror = "1"
```

### 6.3 Sidecar 管理器

```rust
// src-tauri/src/sidecar/manager.rs

use std::process::{Child, Command, Stdio};
use std::sync::{Arc, Mutex};
use std::io::{BufRead, BufReader, Write};
use tokio::sync::{mpsc, oneshot};
use serde_json::Value;

pub struct SidecarManager {
    child: Arc<Mutex<Option<Child>>>,
    request_tx: mpsc::UnboundedSender<SidecarRequest>,
}

struct SidecarRequest {
    id: u64,
    cmd: String,
    params: Value,
    response_tx: oneshot::Sender<Result<Value, String>>,
}

impl SidecarManager {
    pub fn new(app_handle: &tauri::AppHandle) -> Result<Self, SidecarError> {
        let sidecar_path = app_handle
            .path()
            .sidecar_path("macast-sidecar")
            .map_err(|e| SidecarError::PathError(e.to_string()))?;

        let child = Command::new(&sidecar_path)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|e| SidecarError::SpawnError(e.to_string()))?;

        let (tx, rx) = mpsc::unbounded_channel();
        let manager = Self {
            child: Arc::new(Mutex::new(Some(child))),
            request_tx: tx,
        };

        manager.start_io_thread(rx);
        Ok(manager)
    }

    pub async fn call(&self, cmd: &str, params: Value) -> Result<Value, String> {
        let (tx, rx) = oneshot::channel();
        static COUNTER: std::sync::atomic::AtomicU64 =
            std::sync::atomic::AtomicU64::new(0);

        let id = COUNTER.fetch_add(1, std::sync::atomic::Ordering::Relaxed);

        self.request_tx
            .send(SidecarRequest {
                id,
                cmd: cmd.to_string(),
                params,
                response_tx: tx,
            })
            .map_err(|_| "Sidecar channel closed".to_string())?;

        rx.await
            .map_err(|_| "Sidecar response dropped".to_string())?
    }

    fn start_io_thread(
        &self,
        mut rx: mpsc::UnboundedReceiver<SidecarRequest>,
    ) {
        let child_ref = self.child.clone();

        std::thread::spawn(move || {
            let mut child_guard = child_ref.lock().unwrap();
            let child = child_guard.as_mut().unwrap();
            let stdin = child.stdin.as_mut().unwrap();
            let stdout = child.stdout.as_mut().unwrap();
            let mut reader = BufReader::new(stdout);

            while let Some(req) = rx.blocking_recv() {
                // 构建请求 JSON
                let request = serde_json::json!({
                    "id": req.id,
                    "cmd": req.cmd,
                    "params": req.params
                });

                // 写入 stdin
                if writeln!(stdin, "{}", request).is_err() {
                    let _ = req.response_tx.send(
                        Err("Failed to write to sidecar".into())
                    );
                    continue;
                }
                stdin.flush().ok();

                // 读取响应
                let mut line = String::new();
                match reader.read_line(&mut line) {
                    Ok(_) => {
                        match serde_json::from_str::<Value>(&line) {
                            Ok(resp) => {
                                if resp["success"].as_bool().unwrap_or(false) {
                                    let _ = req.response_tx.send(
                                        Ok(resp["data"].clone())
                                    );
                                } else {
                                    let err = resp["error"]
                                        .as_str()
                                        .unwrap_or("Unknown error");
                                    let _ = req.response_tx.send(
                                        Err(err.to_string())
                                    );
                                }
                            }
                            Err(e) => {
                                let _ = req.response_tx.send(
                                    Err(format!("JSON parse error: {}", e))
                                );
                            }
                        }
                    }
                    Err(e) => {
                        let _ = req.response_tx.send(
                            Err(format!("Read error: {}", e))
                        );
                    }
                }
            }
        });
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        if let Some(mut child) = self.child.lock().unwrap().take() {
            // 发送退出命令
            let stdin = child.stdin.as_mut();
            if let Some(stdin) = stdin {
                writeln!(stdin, r#"{{"cmd":"exit","params":{{}}}}"#).ok();
                stdin.flush().ok();
            }
            // 等待退出或强制杀死
            match child.wait() {
                Ok(_) => {}
                Err(_) => { child.kill().ok(); }
            }
        }
    }
}

#[derive(Debug, thiserror::Error)]
pub enum SidecarError {
    #[error("Sidecar path error: {0}")]
    PathError(String),
    #[error("Failed to spawn sidecar: {0}")]
    SpawnError(String),
}
```

### 6.4 Tauri 命令定义

```rust
// src-tauri/src/commands/device.rs
use tauri::State;
use crate::sidecar::manager::SidecarManager;
use serde::{Deserialize, Serialize};

#[derive(Debug, Serialize, Deserialize)]
pub struct Device {
    pub id: String,
    pub name: String,
    #[serde(rename = "type")]
    pub device_type: String,
    pub ip: String,
    pub port: u16,
    pub status: String,
    pub is_default: bool,
    pub manufacturer: Option<String>,
    pub model_name: Option<String>,
    pub udn: String,
}

#[tauri::command]
pub async fn get_devices(
    sidecar: State<'_, SidecarManager>,
) -> Result<Vec<Device>, String> {
    let data = sidecar.call("get_devices", serde_json::json!({})).await?;
    serde_json::from_value(data).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn refresh_devices(
    sidecar: State<'_, SidecarManager>,
) -> Result<Vec<Device>, String> {
    let data = sidecar.call("refresh_devices", serde_json::json!({})).await?;
    serde_json::from_value(data).map_err(|e| e.to_string())
}

// src-tauri/src/commands/cast.rs
#[tauri::command]
pub async fn start_cast(
    sidecar: State<'_, SidecarManager>,
    device_id: String,
    media_uri: String,
) -> Result<(), String> {
    sidecar.call("start_cast", serde_json::json!({
        "device_id": device_id,
        "media_uri": media_uri
    })).await?;
    Ok(())
}

#[tauri::command]
pub async fn stop_cast(
    sidecar: State<'_, SidecarManager>,
) -> Result<(), String> {
    sidecar.call("stop_cast", serde_json::json!({})).await?;
    Ok(())
}

#[tauri::command]
pub async fn pause_cast(
    sidecar: State<'_, SidecarManager>,
) -> Result<(), String> {
    sidecar.call("pause_cast", serde_json::json!({})).await?;
    Ok(())
}

#[tauri::command]
pub async fn resume_cast(
    sidecar: State<'_, SidecarManager>,
) -> Result<(), String> {
    sidecar.call("resume_cast", serde_json::json!({})).await?;
    Ok(())
}

#[tauri::command]
pub async fn seek_cast(
    sidecar: State<'_, SidecarManager>,
    position: String,
) -> Result<(), String> {
    sidecar.call("seek_cast", serde_json::json!({
        "position": position
    })).await?;
    Ok(())
}

// src-tauri/src/commands/media.rs
#[derive(Debug, Serialize, Deserialize)]
pub struct MediaInfo {
    #[serde(rename = "type")]
    pub media_type: String,
    pub uri: String,
    pub title: String,
    pub duration: Option<f64>,
    pub mime_type: String,
    pub file_size: Option<u64>,
    pub thumbnail: Option<String>,
}

#[tauri::command]
pub async fn parse_media_file(
    sidecar: State<'_, SidecarManager>,
    file_path: String,
) -> Result<MediaInfo, String> {
    let data = sidecar.call("parse_media", serde_json::json!({
        "type": "file",
        "path": file_path
    })).await?;
    serde_json::from_value(data).map_err(|e| e.to_string())
}

#[tauri::command]
pub async fn parse_media_url(
    sidecar: State<'_, SidecarManager>,
    url: String,
) -> Result<MediaInfo, String> {
    let data = sidecar.call("parse_media", serde_json::json!({
        "type": "url",
        "url": url
    })).await?;
    serde_json::from_value(data).map_err(|e| e.to_string())
}
```

### 6.5 主入口

```rust
// src-tauri/src/main.rs
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

mod commands;
mod sidecar;
mod window;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .setup(|app| {
            // 初始化 Sidecar
            let sidecar = sidecar::manager::SidecarManager::new(app.handle())?;
            app.manage(sidecar);

            // 应用窗口特效
            if let Some(window) = app.get_webview_window("main") {
                window::effect::apply(&window);
            }

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            commands::device::get_devices,
            commands::device::refresh_devices,
            commands::cast::start_cast,
            commands::cast::stop_cast,
            commands::cast::pause_cast,
            commands::cast::resume_cast,
            commands::cast::seek_cast,
            commands::cast::get_cast_state,
            commands::cast::set_volume,
            commands::cast::set_mute,
            commands::media::parse_media_file,
            commands::media::parse_media_url,
            commands::settings::get_settings,
            commands::settings::save_settings,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

---

## 7. 打包与分发

### 7.1 Python Sidecar 打包

```python
# scripts/build_sidecar.py
"""PyInstaller 打包脚本"""

import PyInstaller.__main__

PyInstaller.__main__.run([
    "macast_sidecar/main.py",
    "--name", "macast-sidecar",
    "--onefile",
    "--console",
    "--add-data", "macast_sidecar/xml:macast_sidecar/xml",
    "--hidden-import", "lxml",
    "--hidden-import", "netifaces",
    "--hidden-import", "aiohttp",
])
```

### 7.2 Tauri 配置

```jsonc
// tauri.conf.json
{
  "bundle": {
    "externalBin": [
      "sidecars/macast-sidecar"
    ],
    "resources": [
      "sidecars/macast-sidecar.xml"
    ]
  }
}
```

### 7.3 构建流程

```bash
# 1. 打包 Python Sidecar
cd macast-backend
pip install pyinstaller
python scripts/build_sidecar.py
cp dist/macast-sidecar ../src-tauri/sidecars/

# 2. 构建 Tauri 应用
cd ../src-tauri
cargo tauri build
```

---

## 8. 后端开发任务

### Phase 1: 基础架构
- [ ] 创建 `macast-backend/` Python 项目
- [ ] 实现 `main.py` Sidecar 入口 (stdin/stdout)
- [ ] 实现 `commands.py` 命令路由器
- [ ] 实现 Rust `SidecarManager`
- [ ] 验证 Rust ↔ Python 通信

### Phase 2: SSDP 模块
- [ ] 复用 `ssdp.py`，移除 cherrypy 依赖
- [ ] 改用回调机制通知设备变化
- [ ] 实现 `get_devices` / `refresh_devices` 命令

### Phase 3: DLNA 协议
- [ ] 复用 `protocol.py` 的 DLNA 协议逻辑
- [ ] 用 aiohttp 重写 HTTP 服务（替代 CherryPy）
- [ ] 实现 DLNA 渲染器（接收手机投屏）
- [ ] 实现 DLNA 控制端（投屏到电视）

### Phase 4: MPV 渲染器
- [ ] 复用 `mpv.py`，移除 GUI 回调
- [ ] 实现与 DLNA 协议的集成
- [ ] 测试手机投屏到本机 → MPV 播放

### Phase 5: 投屏控制
- [ ] 实现播放/暂停/停止控制
- [ ] 实现音量控制
- [ ] 实现进度拖拽
- [ ] 实现状态显示

### Phase 6: 媒体服务
- [ ] 实现 `MediaParser` 文件解析
- [ ] 实现 `MediaServer` HTTP 服务（提供本地文件访问）
- [ ] 支持 Range 请求（视频拖拽）

### Phase 7: 打包集成
- [ ] PyInstaller 打包 Python Sidecar
- [ ] 配置 Tauri `externalBin`
- [ ] 端到端测试
- [ ] 跨平台打包验证

---

## 9. 定制完成总结

### 9.1 已完成的工作

基于 `Macast-main/` 原始代码，已完成以下定制：

#### 目录结构创建

```
macast-backend/
├── macast_sidecar/
│   ├── __init__.py
│   ├── main.py                 # Sidecar 入口 (stdin/stdout)
│   ├── commands.py             # 命令路由器
│   ├── ssdp.py                 # SSDP 设备发现
│   ├── protocol/
│   │   ├── __init__.py
│   │   └── dlna.py             # DLNA 协议
│   ├── renderer/
│   │   ├── __init__.py
│   │   ├── base.py             # 渲染器基类
│   │   └── mpv.py              # MPV 渲染器
│   ├── media/
│   │   ├── __init__.py
│   │   ├── parser.py           # 媒体解析
│   │   └── server.py           # 媒体 HTTP 服务
│   ├── types/
│   │   ├── __init__.py
│   │   ├── device.py           # 设备数据结构
│   │   ├── media.py            # 媒体数据结构
│   │   └── cast.py             # 投屏状态
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config.py           # 配置管理
│   │   └── logger.py           # 日志管理
│   └── xml/                    # UPnP 描述文件 (直接复用)
│       ├── Description.xml
│       ├── AVTransport.xml
│       ├── ConnectionManager.xml
│       ├── RenderingControl.xml
│       └── SinkProtocolInfo.csv
├── scripts/
│   └── build_sidecar.py        # PyInstaller 打包脚本
├── tests/
│   └── test_imports.py         # 导入测试
├── pyproject.toml              # 项目配置
├── requirements.txt            # 依赖列表
└── README.md                   # 项目说明
```

#### 代码复用情况

| 模块 | 原始文件 | 改动说明 |
|------|----------|----------|
| SSDP | `macast/ssdp.py` | 移除 cherrypy，改用回调机制 |
| DLNA | `macast/protocol.py` | 移除 CherryPy，保留协议核心逻辑 |
| Renderer | `macast/renderer.py` | 移除 cherrypy.engine，简化为纯接口 |
| MPV | `macast_renderer/mpv.py` | 移除 GUI 回调，移除 cherrypy |
| Config | `macast/utils.py` | 移除 cherrypy，简化为配置管理 |
| XML | `macast/xml/*` | 直接复用，无改动 |

#### 新增模块

| 模块 | 功能 |
|------|------|
| `main.py` | Sidecar 入口，stdin/stdout JSON 通信 |
| `commands.py` | 命令路由器，分发到各模块 |
| `media/parser.py` | 媒体文件解析（本地文件 + URL） |
| `media/server.py` | 本地文件 HTTP 服务（支持 Range 请求） |
| `types/*` | 数据结构定义（Device, MediaInfo, CastState） |

#### 废弃的代码

| 原始文件 | 原因 |
|----------|------|
| `macast/gui.py` | 由 Tauri 前端替代 |
| `macast/macast.py` Macast(App) | 由 Tauri 前端替代 |
| `macast/macast.py` MacastPluginManager | 移除插件系统 |
| `macast/server.py` | 由 aiohttp 服务替代 |

### 9.2 关键改动说明

1. **移除 CherryPy 依赖**
   - 所有 `cherrypy.engine.publish` 调用已移除
   - 改用回调函数机制通知状态变化
   - HTTP 服务改用 `http.server`（轻量）或 `aiohttp`（异步）

2. **移除 GUI 相关代码**
   - 所有 `gui.py`、`Macast(App)` 相关代码已移除
   - 菜单系统、系统托盘等功能由 Tauri 前端替代

3. **添加 Sidecar 通信**
   - 通过 stdin/stdout JSON 与 Rust 通信
   - 支持请求-响应模式
   - 支持事件推送模式

4. **简化架构**
   - 移除插件系统
   - 移除复杂的菜单配置
   - 专注于核心功能：SSDP + DLNA + MPV

### 9.3 下一步工作

1. **测试验证**
   ```bash
   cd macast-backend
   pip install -r requirements.txt
   python -m pytest tests/
   ```

2. **集成 Rust Tauri**
   - 创建 `src-tauri/` 项目
   - 实现 `SidecarManager`
   - 实现 Tauri 命令层

3. **前端 UI**
   - 创建 Vue 3 项目
   - 实现设备列表、文件选择、投屏控制等组件

4. **打包发布**
   - PyInstaller 打包 Python Sidecar
   - Tauri 打包完整应用
