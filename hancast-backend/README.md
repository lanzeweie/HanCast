# HanCast 2.0 Python Sidecar

HanCast 2.0 的 Python 后端，作为 Tauri 应用的 Sidecar 运行。

## 功能

- **SSDP 设备发现**: 自动发现局域网内的 DLNA 设备
- **DLNA 协议**: 支持 DLNA 渲染器（接收投屏）和控制端（发送投屏）
- **MPV 渲染器**: 作为 DLNA 渲染器播放接收的媒体
- **媒体服务**: 提供本地文件的 HTTP 访问
- **投屏控制**: 播放/暂停/停止/音量/进度控制
- **B站解析**: 支持 bilibili.com 视频链接解析

## 架构

```
┌─────────────────────────────────────────────────────────────────┐
│                     HanCast 2.0 单一应用                          │
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
│  │  │ SSDP 发现 │  │ DLNA 协议 │  │ 媒体服务  │  │ 命令路由  │ │   │
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

---

## 调试技巧

### MPV Lua 脚本快速写日志

在 `mpv/portable_config/scripts/` 下的 Lua 脚本中，使用以下模板快速写日志到文件：

```lua
-- 写入诊断文件
local diag_file = io.open("mpv_diag.txt", "a")
local function log(msg)
    if diag_file then
        diag_file:write(os.date("%H:%M:%S") .. " script-name: " .. msg .. "\n")
        diag_file:flush()
    end
end

log("=== script loaded ===")
```

使用方式：
1. 在脚本开头添加上述代码
2. 在需要调试的地方调用 `log("message")`
3. 运行后查看 `mpv_diag.txt` 文件
4. 调试完成后删除日志代码

示例：
```lua
mp.register_event('file-loaded', function()
    log("file-loaded: media-title=" .. mp.get_property("media-title"))
    log("file-loaded: filename=" .. mp.get_property("filename"))
    log("file-loaded: title=" .. mp.get_property("title"))
end)
```

### Python 端日志

Python 端的日志输出到 stderr，在 Tauri 开发模式下会显示在终端中。
