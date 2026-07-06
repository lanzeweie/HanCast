use std::collections::HashMap;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

use serde_json::Value;
use tauri::async_runtime::Receiver;
use tauri::{AppHandle, Emitter};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tauri_plugin_shell::ShellExt;
use tokio::sync::{oneshot, Mutex};

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
    _reader: tauri::async_runtime::JoinHandle<()>,
}

impl SidecarManager {
    /// Spawn the Python sidecar and start the stdout reader.
    pub fn new(app: AppHandle) -> Result<Self, String> {
        let (rx, child) = app
            .shell()
            .command("uv")
            .args(["run", "python", "-m", "macast_sidecar.main"])
            .env("PYTHONIOENCODING", "utf-8")
            .current_dir("../macast-backend")
            .spawn()
            .map_err(|e| format!("Failed to spawn sidecar: {e}"))?;

        let child = Arc::new(Mutex::new(Some(child)));
        let pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>> =
            Arc::new(Mutex::new(HashMap::new()));

        // Background task: read CommandEvents and dispatch
        let pending_clone = Arc::clone(&pending);
        let reader = tauri::async_runtime::spawn(async move {
            Self::reader_loop(rx, pending_clone, app).await;
        });

        Ok(Self {
            child,
            pending,
            next_id: AtomicU64::new(0),
            _reader: reader,
        })
    }

    /// Background reader: process events from the sidecar's stdout/stderr.
    async fn reader_loop(
        mut rx: Receiver<CommandEvent>,
        pending: Arc<Mutex<HashMap<u64, oneshot::Sender<Value>>>>,
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
                    break;
                }
                CommandEvent::Error(err) => {
                    eprintln!("[SidecarManager] Process error: {err}");
                    break;
                }
                _ => {}
            }
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
}

impl Drop for SidecarManager {
    fn drop(&mut self) {
        // Try graceful shutdown: send exit command, then kill
        let child = Arc::clone(&self.child);
        std::thread::spawn(move || {
            // Use std sync for cleanup since we're outside tokio context
            let rt = tokio::runtime::Runtime::new();
            if let Ok(rt) = rt {
                rt.block_on(async {
                    let mut guard = child.lock().await;
                    if let Some(ref mut child) = *guard {
                        let _ = child.write(b"{\"cmd\":\"exit\"}\n");
                    }
                    tokio::time::sleep(std::time::Duration::from_millis(200)).await;
                    if let Some(child) = guard.take() {
                        let _ = child.kill();
                    }
                });
            }
        });
    }
}
