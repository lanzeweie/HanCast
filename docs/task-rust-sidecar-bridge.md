# 任务：实现 Rust SidecarManager — 连通前端与 Python 后端

## 目标

将 `src-tauri/src/lib.rs` 中的 mock Tauri commands 替换为真实的 Python Sidecar 调用，实现前端 → Rust → Python 的完整通信链路。

## 当前状态

- **前端**: Vue 3 + Tauri invoke 调用已完成（mock 数据）
- **Python Sidecar**: 16 个命令已实现，stdin/stdout JSON 协议已验证
- **Rust 壳层**: 只有 mock 数据，需要新增 SidecarManager

## 需要做的事

### 1. 新建 `src-tauri/src/sidecar.rs`

实现 `SidecarManager` 结构体，职责：
- 启动 Python sidecar 子进程（通过 `tauri_plugin_shell` 的 sidecar API）
- 通过 stdin 写入 JSON 请求，stdout 读取 JSON 响应
- 用 `id` 字段匹配请求和响应
- 异步调用接口（tokio oneshot channel）

### 2. 修改 `src-tauri/src/lib.rs`

- 导入 sidecar 模块
- 将所有 mock 命令替换为真实调用（通过 `State<'_, SidecarManager>`）
- 在 `setup()` 中初始化 SidecarManager 并注册到 Tauri state
- 保留系统托盘相关代码不变

### 3. 修改 `src-tauri/Cargo.toml`

- 添加 `tokio` 依赖（需要 `sync` feature）

## 关键约束

### Python Sidecar 协议

**请求格式** (写入 stdin，单行 JSON + 换行):
```json
{"id": 0, "cmd": "get_devices", "params": {}}
```

**响应格式** (从 stdout 读取，单行 JSON + 换行):
```json
{"id": 0, "success": true, "data": [...]}
```
或
```json
{"id": 0, "success": false, "error": "Device not found"}
```

**事件推送** (Python 主动输出，无 id):
```json
{"event": "device_found", "data": {...}}
```

### 16 个命令清单

| 命令 | 参数 | 说明 |
|------|------|------|
| `get_devices` | `{}` | 获取设备列表 |
| `refresh_devices` | `{}` | 触发扫描 |
| `set_default_device` | `{id}` | 设置默认设备 |
| `rename_device` | `{id, name}` | 重命名 |
| `remove_device` | `{id}` | 移除设备 |
| `start_cast` | `{device_id, media_uri}` | 开始投屏 |
| `stop_cast` | `{}` | 停止投屏 |
| `pause_cast` | `{}` | 暂停 |
| `resume_cast` | `{}` | 恢复 |
| `seek_cast` | `{position}` | 跳转 (HH:MM:SS) |
| `get_cast_state` | `{}` | 获取投屏状态 |
| `set_volume` | `{volume}` | 音量 0-100 |
| `set_mute` | `{muted}` | 静音 |
| `parse_media` | `{type, path/url}` | 解析媒体 |
| `get_settings` | `{}` | 获取设置 |
| `save_settings` | `{settings}` | 保存设置 |

### Tauri Command 签名要求

前端 invoke 调用的参数名是 snake_case，Rust 命令参数必须匹配：

```rust
#[tauri::command]
async fn start_cast(
    sidecar: State<'_, SidecarManager>,
    device_id: String,    // 匹配前端 invoke('start_cast', { device_id, media_uri })
    media_uri: String,
) -> Result<(), String> { ... }
```

### Python Sidecar 启动方式

开发阶段直接用 `python -m macast_sidecar.main`，工作目录为 `macast-backend/`。

生产阶段用 PyInstaller 打包的可执行文件，放在 `src-tauri/sidecars/` 目录。

**当前阶段用开发方式**，不要求打包。

## 参考文件

| 文件 | 用途 |
|------|------|
| `src-tauri/src/lib.rs` | 当前 mock 实现，需要改造 |
| `src-tauri/src/main.rs` | 入口，调用 `macast_lib::run()` |
| `src-tauri/Cargo.toml` | 依赖配置 |
| `macast-backend/macast_sidecar/main.py` | Python sidecar 入口 |
| `macast-backend/macast_sidecar/commands.py` | Python 命令路由 |
| `docs/Macast-Backend-Spec.md` | 完整后端设计规格 |
| `docs/Macast-Frontend-API.md` | 前端 API 接口文档 |

## 验收标准

1. `cargo build` 编译通过
2. `npm run tauri dev` 能启动应用
3. Python sidecar 进程自动启动
4. 前端点击"刷新设备"能调用 Python 真实返回（空列表或真实设备）
5. 前端投屏操作能通过 Rust 转发到 Python
6. Python sidecar 进程在 Tauri 退出时自动关闭

## 注意事项

- 不要修改前端代码（`src/` 目录）
- 不要修改 Python 代码（`macast-backend/` 目录）
- 保留 `lib.rs` 中的系统托盘逻辑
- 保留 `minimize_window` 和 `close_window` 命令
- SidecarManager 需要实现 `Drop` trait，退出时清理子进程
