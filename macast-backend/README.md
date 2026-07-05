# Macast 2.0 Python Sidecar

Macast 2.0 的 Python 后端，作为 Tauri 应用的 Sidecar 运行。

## 功能

- **SSDP 设备发现**: 自动发现局域网内的 DLNA 设备
- **DLNA 协议**: 支持 DLNA 渲染器（接收投屏）和控制端（发送投屏）
- **MPV 渲染器**: 作为 DLNA 渲染器播放接收的媒体
- **媒体服务**: 提供本地文件的 HTTP 访问
- **投屏控制**: 播放/暂停/停止/音量/进度控制

## 架构

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
└─────────────────────────────────────────────────────────────────┘
```

## 开发

### 安装依赖

```bash
pip install -r requirements.txt
```

### 运行测试

```bash
python -m pytest
```

### 打包

```bash
python scripts/build_sidecar.py
```

## 通信协议

### 请求格式 (Rust → Python stdin)

```json
{
  "id": 0,
  "cmd": "start_cast",
  "params": {
    "device_id": "uuid-xxxx",
    "media_uri": "http://192.168.1.5:8080/video.mp4"
  }
}
```

### 响应格式 (Python → Rust stdout)

```json
// 成功
{
  "id": 0,
  "success": true,
  "data": { ... }
}

// 失败
{
  "id": 0,
  "success": false,
  "error": "Device not found"
}
```

### 事件格式 (Python → Rust stdout)

```json
{
  "event": "device_found",
  "data": { ... }
}
```

## 命令列表

| 命令 | 参数 | 返回 | 说明 |
|------|------|------|------|
| `get_devices` | `{}` | `Device[]` | 获取已发现设备 |
| `refresh_devices` | `{}` | `Device[]` | 触发扫描并返回 |
| `set_default_device` | `{id}` | `null` | 设为默认设备 |
| `rename_device` | `{id, name}` | `null` | 重命名设备 |
| `remove_device` | `{id}` | `null` | 移除设备 |
| `start_cast` | `{device_id, media_uri}` | `null` | 开始投屏 |
| `stop_cast` | `{}` | `null` | 停止投屏 |
| `pause_cast` | `{}` | `null` | 暂停投屏 |
| `resume_cast` | `{}` | `null` | 恢复投屏 |
| `seek_cast` | `{position}` | `null` | 跳转到指定位置 |
| `get_cast_state` | `{}` | `CastState` | 获取投屏状态 |
| `set_volume` | `{volume}` | `null` | 设置音量 |
| `set_mute` | `{muted}` | `null` | 设置静音 |
| `parse_media` | `{type, path/url}` | `MediaInfo` | 解析媒体 |
| `get_settings` | `{}` | `AppSettings` | 获取设置 |
| `save_settings` | `{settings}` | `null` | 保存设置 |
| `exit` | `{}` | — | 优雅退出 |

## 许可证

GPL-3.0
