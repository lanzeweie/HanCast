# Rust 侧 — Sidecar 桥接层进度

> 最后更新: 2026-07-05

## 已完成

### ✅ Cargo.toml — 依赖配置

添加了 `tokio` 依赖:

```toml
tokio = { version = "1", features = ["sync", "macros", "rt-multi-thread"] }
```

### ✅ sidecar.rs — SidecarManager 实现

**文件**: `src-tauri/src/sidecar.rs`

职责:
- 通过 `tauri_plugin_shell` 启动 Python sidecar 子进程 (`python -m macast_sidecar.main`)
- stdin 写入 JSON 请求, stdout 读取 JSON 响应
- 用 `id` 字段 + `oneshot channel` 匹配请求与响应
- Python 主动推送的事件 (`{"event", "data"}`) 通过 `app.emit()` 转发给前端

核心结构:

```rust
pub struct SidecarManager {
    child:   Arc<Mutex<Option<CommandChild>>>,       // 进程句柄
    pending: Arc<Mutex<HashMap<u64, Sender<Value>>>>, // 请求-响应映射
    next_id: AtomicU64,                               // 单调递增 ID
    _reader: JoinHandle<()>,                          // stdout 读取任务
}
```

通信协议 (与 Python 约定):

| 方向 | 格式 |
|------|------|
| 请求 (Rust→Python) | `{"id": 0, "cmd": "get_devices", "params": {}}` |
| 响应 (Python→Rust) | `{"id": 0, "success": true, "data": [...]}` |
| 事件 (Python→Rust→前端) | `{"event": "device_found", "data": {...}}` |

进程生命周期:
- 启动: `setup()` 中调用 `SidecarManager::new(app.handle().clone())`
- 退出: `Drop` 发送 `{"cmd":"exit"}` → 等待 200ms → `kill()`

### ✅ lib.rs — 全部 16 个 mock 命令替换为真实调用

**文件**: `src-tauri/src/lib.rs`

改造内容:
- `mod sidecar;` 引入模块
- 所有命令改为 `async fn`, 接收 `State<'_, SidecarManager>`
- `setup()` 中初始化 `SidecarManager` 并注册到 Tauri state
- 保留 `minimize_window`、`close_window` 和系统托盘逻辑不变

命令映射表:

| Tauri Command | Python 命令 | 参数映射 |
|---|---|---|
| `get_devices` | `get_devices` | `{}` |
| `refresh_devices` | `refresh_devices` | `{}` |
| `set_default_device(id)` | `set_default_device` | `{"id": id}` |
| `rename_device(id, name)` | `rename_device` | `{"id": id, "name": name}` |
| `remove_device(id)` | `remove_device` | `{"id": id}` |
| `parse_media_file(file_path)` | `parse_media` | `{"type": "file", "path": file_path}` |
| `parse_media_url(url)` | `parse_media` | `{"type": "url", "url": url}` |
| `start_cast(device_id, media_uri)` | `start_cast` | `{"device_id", "media_uri"}` |
| `stop_cast` | `stop_cast` | `{}` |
| `pause_cast` | `pause_cast` | `{}` |
| `resume_cast` | `resume_cast` | `{}` |
| `seek_cast(position)` | `seek_cast` | `{"position": position}` |
| `get_cast_state` | `get_cast_state` | `{}` |
| `set_volume(volume)` | `set_volume` | `{"volume": volume}` |
| `set_mute(muted)` | `set_mute` | `{"muted": muted}` |
| `get_settings` | `get_settings` | `{}` |
| `save_settings(settings)` | `save_settings` | `{"settings": settings}` |

注意: 前端有 `parse_media_file` 和 `parse_media_url` 两个命令, Python 只有一个 `parse_media` (用 `type` 参数区分), Rust 层做了桥接。

## 编译状态

```
cargo build → ✅ 通过
```

## 未做 / 后续

| 项目 | 说明 |
|------|------|
| `tauri dev` 端到端测试 | 需要 Python 环境 + 依赖安装后才能跑 |
| Tauri capabilities 配置 | shell 插件可能需要 capabilities JSON 授权 sidecar 执行 |
| 生产打包 | 当前用 `python -m` 启动, 生产需 PyInstaller 打包 + sidecar 二进制 |
| 错误恢复 | sidecar 崩溃后暂无自动重启机制 |
| 事件类型完善 | `device_lost`、`cast_state_changed`、`cast_error` 等事件由 Python 推送, Rust 只做透传 |
