use std::collections::HashMap;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;

use serde_json::Value;
use tauri::async_runtime::Receiver;
use tauri::{AppHandle, Emitter};
#[cfg(not(debug_assertions))]
use tauri::Manager;
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tokio::sync::{oneshot, Mutex};

/// 在指定目录中查找以 `hancast-sidecar` 开头的可执行文件
///
/// 不限定具体 triple 后缀，适配所有命名形式：
///   hancast-sidecar.exe / hancast-sidecar-{triple}.exe  (Windows)
///   hancast-sidecar    / hancast-sidecar-{triple}       (Linux/macOS)
///
/// - 按文件名排序，确保同目录下多个候选时选择结果稳定
/// - Linux/macOS 下验证文件具有执行权限
/// - 错误信息中包含目录实际内容，便于调试
#[cfg(not(debug_assertions))]
fn find_sidecar_binary(resource_dir: &std::path::Path) -> Result<std::path::PathBuf, String> {
    if !resource_dir.is_dir() {
        return Err(format!("Resource directory not found: {:?}", resource_dir));
    }

    let entries = std::fs::read_dir(resource_dir)
        .map_err(|e| format!("Failed to read resource dir {}: {}", resource_dir.display(), e))?;

    // 收集所有候选文件，按文件名排序确保选择结果稳定
    let mut candidates: Vec<std::path::PathBuf> = Vec::new();
    for entry in entries {
        let entry = entry.map_err(|e| format!("Failed to read directory entry: {e}"))?;
        let path = entry.path();

        if !path.is_file() {
            continue;
        }

        if let Some(file_name) = path.file_name().and_then(|n| n.to_str()) {
            // 匹配所有 hancast-sidecar 开头的可执行文件（不限 triple）
            if !file_name.starts_with("hancast-sidecar") {
                continue;
            }

            if cfg!(target_os = "windows") {
                if !file_name.ends_with(".exe") {
                    continue;
                }
            } else {
                if file_name.ends_with(".exe") {
                    continue;
                }
            }

            candidates.push(path);
        }
    }

    candidates.sort_by(|a, b| a.file_name().cmp(&b.file_name()));

    // 依次尝试，找到第一个可执行的
    for path in candidates {
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            if let Ok(meta) = std::fs::metadata(&path) {
                if meta.permissions().mode() & 0o111 == 0 {
                    eprintln!("[Sidecar] Skipping (no execute permission): {:?}", path);
                    continue;
                }
            }
        }

        return Ok(path);
    }

    // 构建详细的错误信息，列出目录实际内容
    let dir_listing = std::fs::read_dir(resource_dir)
        .map(|entries| {
            entries
                .filter_map(|e| e.ok())
                .map(|e| format!("  {}", e.file_name().to_string_lossy()))
                .collect::<Vec<_>>()
                .join("\n")
        })
        .unwrap_or_else(|e| format!("  (无法读取: {e})"));

    let expected_ext = if cfg!(target_os = "windows") { ".exe" } else { "" };
    Err(format!(
        "No hancast-sidecar-*{expected_ext} binary found in {}\nDirectory contents:\n{dir_listing}",
        resource_dir.display(),
    ))
}

/// Manages the Python sidecar process.
///
/// Communicates via stdin/stdout JSON protocol:
///   Request:  {"id": <u64>, "cmd": <string>, "params": <object>}
///   Response: {"id": <u64>, "success": <bool>, "data": <any>, "error": <string>}
///   Event:    {"event": <string>, "data": <object>}
pub struct SidecarManager {
    child: Arc<Mutex<Option<CommandChild>>>,
    pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>>,
    next_id: AtomicU64,
    /// 收到 CommandEvent::Terminated，确认子进程已退出
    terminated: Arc<AtomicBool>,
    /// reader_loop 发生错误（事件流中断），不等同于进程退出
    reader_failed: Arc<AtomicBool>,
    _reader: tauri::async_runtime::JoinHandle<()>,
}

impl SidecarManager {
    /// Spawn the Python sidecar and start the stdout reader.
    ///
    /// - Dev (`cargo tauri dev`):     `uv run python -m hancast_sidecar.main`
    /// - Prod (`cargo tauri build`):  bundled Nuitka sidecar binary
    pub fn new(app: AppHandle) -> Result<Self, String> {
        let (rx, child) = {
            #[cfg(debug_assertions)]
            {
                let backend_dir = "../hancast-backend";
                if !std::path::Path::new(backend_dir).is_dir() {
                    return Err(format!(
                        "Python backend directory not found: {}\n\
                         Make sure you run `cargo tauri dev` from the project root (src-tauri/).",
                        backend_dir
                    ));
                }
                app.shell()
                    .command("uv")
                    .args(["run", "python", "-m", "hancast_sidecar.main"])
                    .env("PYTHONIOENCODING", "utf-8")
                    .current_dir(backend_dir)
                    .spawn()
                    .map_err(|e| format!("Failed to spawn sidecar via uv: {e}"))?
            }
            #[cfg(not(debug_assertions))]
            {
                // Nuitka standalone 需要工作目录为依赖所在目录
                // 依赖文件平铺在 resource_dir 根目录（*.dll, *.pyd, hancast_sidecar/ 等）
                let resource_dir = app
                    .path()
                    .resource_dir()
                    .map_err(|e| format!("Failed to get resource dir: {e}"))?;

                eprintln!("[Sidecar] resource_dir: {:?}", resource_dir);

                // 模糊查找 hancast-sidecar- 开头的可执行文件（自动适配任意平台 triple）
                let sidecar_path = find_sidecar_binary(&resource_dir)?;
                eprintln!("[Sidecar] Found sidecar: {:?}", sidecar_path);

                // 使用 command() + 绝对路径，绕过 sidecar() 的目录剥离问题
                // current_dir 设为 sidecar 同级目录，确保 DLL/SO 依赖能正确加载
                let work_dir = sidecar_path
                    .parent()
                    .unwrap_or(&resource_dir)
                    .to_path_buf();

                app.shell()
                    .command(&sidecar_path)
                    .env("PYTHONIOENCODING", "utf-8")
                    .current_dir(&work_dir)
                    .spawn()
                    .map_err(|e| format!("Failed to spawn sidecar {:?}: {e}", sidecar_path))?
            }
        };

        let child = Arc::new(Mutex::new(Some(child)));
        let pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>> =
            Arc::new(Mutex::new(HashMap::new()));
        let terminated = Arc::new(AtomicBool::new(false));
        let reader_failed = Arc::new(AtomicBool::new(false));

        // Background task: read CommandEvents and dispatch
        let pending_clone = Arc::clone(&pending);
        let terminated_clone = Arc::clone(&terminated);
        let reader_failed_clone = Arc::clone(&reader_failed);
        let reader = tauri::async_runtime::spawn(async move {
            Self::reader_loop(rx, pending_clone, terminated_clone, reader_failed_clone, app)
                .await;
        });

        Ok(Self {
            child,
            pending,
            next_id: AtomicU64::new(0),
            terminated,
            reader_failed,
            _reader: reader,
        })
    }

    /// Background reader: process events from the sidecar's stdout/stderr.
    ///
    /// 事件来源（tauri-plugin-shell 2.3.5 源码）：
    /// - `Terminated`：来自独立的 `child.wait()` 线程，`wait()` 成功返回时发送
    /// - `Error`：来自管道读取线程的 I/O 错误，或 `wait()` 调用失败
    ///
    /// 处理策略：
    /// - `Terminated` → `terminated = true`，break
    /// - `Error`      → `reader_failed = true`，不 break。
    ///   管道读取错误不影响 `wait()` 线程，Terminated 仍会到达；
    ///   break 会导致无法接收 Terminated，使 shutdown 无法确认退出。
    ///
    /// When the stream ends, drains all pending senders with an error response
    /// so no caller hangs forever.
    async fn reader_loop(
        mut rx: Receiver<CommandEvent>,
        pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>>,
        terminated: Arc<AtomicBool>,
        reader_failed: Arc<AtomicBool>,
        app: AppHandle,
    ) {
        while let Some(event) = rx.recv().await {
            match event {
                CommandEvent::Stdout(bytes) => {
                    let line = String::from_utf8_lossy(&bytes);
                    let trimmed = line.trim();
                    if trimmed.is_empty() {
                        continue;
                    }
                    match serde_json::from_str::<Value>(trimmed) {
                        Ok(val) => {
                            if let Some(id) = val.get("id").and_then(|v| v.as_u64()) {
                                // Response to a request
                                let mut map = pending.lock().await;
                                if let Some(tx) = map.remove(&id) {
                                    let _ = tx.send(val);
                                }
                            } else if let Some(event_name) =
                                val.get("event").and_then(|v| v.as_str())
                            {
                                // Event pushed by Python
                                let data = val.get("data").cloned().unwrap_or(Value::Null);
                                let _ = app.emit(event_name, data);
                            }
                        }
                        Err(e) => {
                            eprintln!("[SidecarManager] Invalid JSON from stdout: {e}");
                        }
                    }
                }
                CommandEvent::Stderr(bytes) => {
                    let line = String::from_utf8_lossy(&bytes);
                    eprint!("[Sidecar stderr] {}", line);
                }
                CommandEvent::Terminated(status) => {
                    eprintln!(
                        "[SidecarManager] Process terminated with code {:?}",
                        status.code
                    );
                    terminated.store(true, Ordering::SeqCst);
                    break;
                }
                CommandEvent::Error(err) => {
                    // 事件流错误 ≠ 进程退出。不 break：
                    // reader_loop 一旦退出就无法再接收后续 Terminated 事件，
                    // 导致 shutdown() 强杀后永远无法确认退出。
                    // 继续循环，让 rx.recv() 在通道关闭时自然退出。
                    eprintln!("[SidecarManager] Process error: {err}");
                    reader_failed.store(true, Ordering::SeqCst);
                }
                _ => {}
            }
        }

        // Sidecar 退出/崩溃：通知所有等待中的请求，防止永久挂起
        let mut map = pending.lock().await;
        for (id, tx) in map.drain() {
            eprintln!("[SidecarManager] Draining pending request #{id}");
            let _ = tx.send(serde_json::json!({
                "success": false,
                "error": "Sidecar process exited unexpectedly"
            }));
        }
    }

    /// Send a command to the sidecar and wait for the response.
    pub async fn send_command(&self, cmd: &str, params: Value) -> Result<Value, String> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);

        let request = serde_json::json!({
            "id": id,
            "cmd": cmd,
            "params": params,
        });

        // Register pending response channel
        let (tx, rx) = oneshot::channel();
        {
            let mut map = self.pending.lock().await;
            map.insert(id, tx);
        }

        // Write request to stdin (synchronous write through Mutex)
        {
            let mut guard = self.child.lock().await;
            let child = guard
                .as_mut()
                .ok_or_else(|| "Sidecar process not running".to_string())?;
            let line = format!("{}\n", serde_json::to_string(&request).unwrap());
            child
                .write(line.as_bytes())
                .map_err(|e| format!("Failed to write to sidecar: {e}"))?;
        }

        // Wait for response
        let response = rx
            .await
            .map_err(|_| "Sidecar process exited unexpectedly".to_string())?;

        // Check success
        if response
            .get("success")
            .and_then(|v| v.as_bool())
            .unwrap_or(false)
        {
            Ok(response.get("data").cloned().unwrap_or(Value::Null))
        } else {
            let error = response
                .get("error")
                .and_then(|v| v.as_str())
                .unwrap_or("Unknown error")
                .to_string();
            Err(error)
        }
    }

    /// 优雅关闭：发送 exit 命令 → 轮询等待 sidecar 真正退出 → 超时后强制 kill
    ///
    /// - `terminated == true`：已收到 Terminated 事件，进程确认退出，跳过 kill
    /// - `reader_failed == true`：事件流错误，进程状态未知，仍需尝试 kill
    /// - 超时：强制 kill 后再次轮询 terminated 确认退出
    ///
    /// 在应用退出前由 quit 事件调用，不依赖 Drop（Drop 中的异步等待不可靠）。
    pub async fn shutdown(&self) {
        // 1. 发送 exit 命令（Python 收到后执行 cleanup 并退出主循环）
        {
            let mut guard = self.child.lock().await;
            if let Some(ref mut child) = *guard {
                let _ = child.write(b"{\"cmd\":\"exit\"}\n");
            }
        }

        // 2. 轮询等待 sidecar 真正退出（reader_loop 置 terminated 标志）
        let timeout_ms: u64 = if cfg!(target_os = "windows") { 3000 } else { 1000 };
        let poll_interval = std::time::Duration::from_millis(50);
        let deadline = std::time::Instant::now() + std::time::Duration::from_millis(timeout_ms);

        while !self.terminated.load(Ordering::SeqCst) {
            if std::time::Instant::now() >= deadline {
                eprintln!("[SidecarManager] shutdown: timeout waiting for sidecar exit");
                break;
            }
            tokio::time::sleep(poll_interval).await;
        }

        // 3. 只有 terminated 才跳过 kill；reader_failed 时进程状态未知，仍需 kill
        if self.reader_failed.load(Ordering::SeqCst) {
            eprintln!("[SidecarManager] shutdown: reader failed, sidecar state unknown");
        }
        if !self.terminated.load(Ordering::SeqCst) {
            let mut guard = self.child.lock().await;
            if let Some(child) = guard.take() {
                eprintln!("[SidecarManager] shutdown: force killing sidecar");
                if let Err(e) = child.kill() {
                    // kill 失败：进程可能已退出，也可能无法终止
                    eprintln!("[SidecarManager] shutdown: kill failed: {e}");
                }
            }
            // 4. kill 后再次确认退出（最多等 500ms）
            let kill_deadline =
                std::time::Instant::now() + std::time::Duration::from_millis(500);
            while !self.terminated.load(Ordering::SeqCst)
                && std::time::Instant::now() < kill_deadline
            {
                tokio::time::sleep(poll_interval).await;
            }
            if !self.terminated.load(Ordering::SeqCst) {
                eprintln!("[SidecarManager] shutdown: sidecar not confirmed exited after kill");
            }
        } else {
            // 已确认退出，释放 child 引用
            let mut guard = self.child.lock().await;
            let _ = guard.take();
        }
    }
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        // Drop 作为兜底：不使用 async runtime（进程退出时不可靠）
        // 优雅关闭由 app 退出前的显式 shutdown 流程负责
        self._reader.abort();

        // 同步杀子进程 — 不等待、不发命令（可能已关闭）
        if let Ok(mut guard) = self.child.try_lock() {
            if let Some(child) = guard.take() {
                eprintln!("[SidecarManager] Drop: killing sidecar process");
                let _ = child.kill();
            }
        }
    }
}
