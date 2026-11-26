mod platform_autostart;
mod sidecar;

use serde::{Deserialize, Serialize};
use sidecar::SidecarManager;
use std::sync::atomic::{AtomicU8, Ordering};
use std::sync::{Arc, Mutex};
use std::fs;
use std::path::PathBuf;
use tauri::{
    menu::{CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, State,
};
#[cfg(target_os = "macos")]
use tauri::menu::{AboutMetadata, Menu as AppMenu, PredefinedMenuItem, Submenu};
use tauri_plugin_clipboard_manager::ClipboardExt;
use chrono::Local;

/// 退出清理状态：0=运行中，1=清理中，2=清理完成。
/// `AppHandle::exit()` 会再次触发 `RunEvent::ExitRequested`，没有状态机会无限
/// 阻止退出；清理期间重复的退出请求也继续拦下，避免提前退出留下孤儿 MPV。
static EXIT_STATE: AtomicU8 = AtomicU8::new(0);
const EXIT_CLEANING: u8 = 1;
const EXIT_READY: u8 = 2;

/// 窗口配置数据结构（尺寸为逻辑像素 / CSS px，与 tauri.conf 一致）
#[derive(Debug, Serialize, Deserialize, Clone)]
struct WindowConfig {
    /// 窗口宽度（逻辑像素）
    width: f64,
    /// 窗口高度（逻辑像素）
    height: f64,
}

impl Default for WindowConfig {
    fn default() -> Self {
        Self {
            width: 434.0,
            height: 634.0,
        }
    }
}

/// 窗口配置状态（用于防抖）
#[derive(Clone)]
struct WindowConfigState {
    config: Arc<Mutex<WindowConfig>>,
    config_path: PathBuf,
    save_timer: Arc<Mutex<Option<tauri::async_runtime::JoinHandle<()>>>>,
}

impl WindowConfigState {
    /// 加载配置文件
    fn load(config_path: &PathBuf) -> Self {
        let config = if config_path.exists() {
            match std::fs::read_to_string(config_path) {
                Ok(content) => serde_json::from_str(&content).unwrap_or_default(),
                Err(_) => WindowConfig::default(),
            }
        } else {
            WindowConfig::default()
        };

        Self {
            config: Arc::new(Mutex::new(config)),
            config_path: config_path.clone(),
            save_timer: Arc::new(Mutex::new(None)),
        }
    }

    /// 更新配置并触发延迟保存（使用后台线程实现防抖）
    fn update_and_save(&self, new_config: WindowConfig) {
        // 更新内存中的配置
        {
            let mut config = self.config.lock().unwrap();
            *config = new_config;
        }

        // 取消之前的保存任务
        {
            let mut timer = self.save_timer.lock().unwrap();
            if let Some(handle) = timer.take() {
                handle.abort();
            }
        }

        // 启动新的延迟保存任务（500ms 防抖）
        let config_ref = self.config.clone();
        let path = self.config_path.clone();
        let timer_ref = self.save_timer.clone();

        let handle = tauri::async_runtime::spawn(async move {
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;

            let config = config_ref.lock().unwrap().clone();
            if let Ok(json) = serde_json::to_string_pretty(&config) {
                if let Some(parent) = path.parent() {
                    let _ = std::fs::create_dir_all(parent);
                }
                let _ = std::fs::write(&path, json);
            }

            // 清除定时器引用
            let mut timer = timer_ref.lock().unwrap();
            *timer = None;
        });

        // 保存新的定时器句柄
        let mut timer = self.save_timer.lock().unwrap();
        *timer = Some(handle);
    }

    /// 获取当前配置
    fn get_config(&self) -> WindowConfig {
        self.config.lock().unwrap().clone()
    }
}

/// 当前投屏 URL 缓存（供托盘菜单使用）
struct CastUrlState {
    url: Arc<Mutex<String>>,
}

/// 会话日志：每次启动写入新文件，同时输出到 stderr
struct SessionLogger {
    path: PathBuf,
}

impl SessionLogger {
    fn new(log_dir: &std::path::Path) -> Self {
        fs::create_dir_all(log_dir).ok();
        let path = log_dir.join("hancast.log");
        // 每次启动清空旧日志
        fs::write(&path, "").ok();
        Self { path }
    }

    fn log(&self, msg: &str) {
        let ts = Local::now().format("%Y-%m-%d %H:%M:%S");
        let line = format!("[{}] {}\n", ts, msg);
        eprint!("{}", line);
        fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&self.path)
            .and_then(|mut f| {
                use std::io::Write;
                f.write_all(line.as_bytes())
            })
            .ok();
    }
}

/// macOS 应用防火墙状态（socketfilterfw 的全局状态）。
///
/// 首次接收投屏时系统可能弹「允许传入连接」；拒绝后 SSDP(1900/UDP) 与
/// DLNA(8080/TCP) 都会被拦截。状态用于设置页指引与启动日志。
#[derive(Debug, Serialize, Clone)]
#[serde(rename_all = "camelCase")]
struct FirewallStatus {
    supported: bool,
    /// socketfilterfw 的 State：0=关闭，1=开启，2=阻止所有传入连接
    state: u8,
    enabled: bool,
    block_all: bool,
    stealth: bool,
    detail: String,
}

#[cfg(target_os = "macos")]
fn read_firewall_status() -> FirewallStatus {
    let mut status = FirewallStatus {
        supported: true,
        state: 0,
        enabled: false,
        block_all: false,
        stealth: false,
        detail: String::new(),
    };

    match std::process::Command::new("/usr/libexec/ApplicationFirewall/socketfilterfw")
        .arg("--getglobalstate")
        .output()
    {
        Ok(out) => {
            let text = String::from_utf8_lossy(&out.stdout).trim().to_string();
            // 输出形如 "Firewall is enabled. (State = 1)"
            if let Some(idx) = text.find("State = ") {
                status.state = text[idx + "State = ".len()..]
                    .chars()
                    .next()
                    .and_then(|c| c.to_digit(10))
                    .unwrap_or(0) as u8;
            }
            status.enabled = status.state != 0;
            status.block_all = status.state == 2;
            status.detail = text;
        }
        Err(e) => {
            status.detail = format!("无法读取防火墙状态: {e}");
        }
    }

    if let Ok(out) = std::process::Command::new("/usr/libexec/ApplicationFirewall/socketfilterfw")
        .arg("--getstealthmode")
        .output()
    {
        status.stealth = String::from_utf8_lossy(&out.stdout).contains(" on");
    }

    status
}

#[cfg(not(target_os = "macos"))]
fn read_firewall_status() -> FirewallStatus {
    FirewallStatus {
        supported: false,
        state: 0,
        enabled: false,
        block_all: false,
        stealth: false,
        detail: "仅 macOS 使用应用防火墙".to_string(),
    }
}

#[cfg(target_os = "macos")]
fn log_firewall_status(logger: &SessionLogger) {
    let status = read_firewall_status();
    if status.block_all {
        logger.log(
            "防火墙已开启（阻止所有传入连接）：手机将无法发现或连接到本机，\
             请在 系统设置 → 网络 → 防火墙 → 选项 中放行 HanCast",
        );
    } else if status.enabled {
        logger.log(
            "防火墙已开启：首次接收投屏若出现“允许传入连接”请选择允许；\
             误点拒绝后需在 系统设置 → 网络 → 防火墙 → 选项 中放行 HanCast/hancast-sidecar",
        );
    } else {
        logger.log("防火墙未开启：接收投屏不受应用防火墙限制");
    }
}

#[tauri::command]
fn get_firewall_status() -> FirewallStatus {
    read_firewall_status()
}

/// 打开系统防火墙设置面板（macOS 14+ 在“网络”设置内）。
#[tauri::command]
fn open_firewall_settings() -> Result<(), String> {
    #[cfg(target_os = "macos")]
    {
        for url in [
            "x-apple.systempreferences:com.apple.Network-Settings.extension?Firewall",
            "x-apple.systempreferences:com.apple.Network-Settings.extension",
            "x-apple.systempreferences:com.apple.preference.security?Firewall",
        ] {
            if std::process::Command::new("/usr/bin/open")
                .arg(url)
                .status()
                .map(|s| s.success())
                .unwrap_or(false)
            {
                return Ok(());
            }
        }
        Err("无法打开系统防火墙设置".to_string())
    }
    #[cfg(not(target_os = "macos"))]
    {
        Err("仅 macOS 支持该操作".to_string())
    }
}

#[tauri::command]
fn minimize_window(window: tauri::Window) {
    window.minimize().ok();
}

#[tauri::command]
fn close_window(window: tauri::Window) {
    // Hide to tray instead of closing
    window.hide().ok();
}

/// macOS 本地网络隐私授权。
///
/// SSDP 多播由 Python sidecar 执行，但 sidecar 不是 App Bundle，TCC 无法为它
/// 弹授权窗口，会直接静默拒绝（sendto 返回 EHOSTUNREACH）。先由主 App 访问
/// 本地网络（TCP 连默认网关 + SSDP 多播），让弹窗归属到 HanCast 主 App；
/// 授权后 sidecar 的发送才会被放行。
#[cfg(target_os = "macos")]
fn warm_up_local_network(logger: &SessionLogger) {
    use std::net::{SocketAddr, TcpStream, UdpSocket};
    use std::time::Duration;

    // 1) TCP 连接默认网关：比 UDP 多播更可靠地触发 Local Network 授权
    if let Some(gateway) = default_gateway() {
        for port in [80u16, 53, 443] {
            let addr = SocketAddr::from((gateway, port));
            match TcpStream::connect_timeout(&addr, Duration::from_millis(300)) {
                Ok(_) => {
                    logger.log(&format!("本地网络授权探测：已连接网关 {addr}"));
                    break;
                }
                Err(e) => logger.log(&format!("本地网络探测 {addr}: {e}")),
            }
        }
    } else {
        logger.log("本地网络探测：未找到默认网关");
    }

    // 2) SSDP 多播探测（应用本身的第一条业务报文）
    let probe: &[u8] = b"M-SEARCH * HTTP/1.1\r\n\
HOST: 239.255.255.250:1900\r\n\
MAN: \"ssdp:discover\"\r\n\
MX: 1\r\n\
ST: ssdp:all\r\n\r\n";

    match UdpSocket::bind("0.0.0.0:0") {
        Ok(sock) => {
            sock.set_multicast_ttl_v4(2).ok();
            match sock.send_to(probe, "239.255.255.250:1900") {
                Ok(n) => logger.log(&format!("本地网络授权探测已发送 ({n} bytes)")),
                Err(e) => logger.log(&format!(
                    "本地网络探测发送失败（尚未授权时属正常）: {e}"
                )),
            }
        }
        Err(e) => logger.log(&format!("本地网络探测 socket 创建失败: {e}")),
    }
}

/// 读取默认路由网关（`route -n get default` 输出中的 gateway 行）。
#[cfg(target_os = "macos")]
fn default_gateway() -> Option<std::net::Ipv4Addr> {
    let output = std::process::Command::new("/sbin/route")
        .args(["-n", "get", "default"])
        .output()
        .ok()?;
    let text = String::from_utf8_lossy(&output.stdout);
    let value = text
        .lines()
        .find_map(|line| line.trim().strip_prefix("gateway:"))?
        .trim();
    value.parse().ok()
}

// ── Device management ──

#[tauri::command]
async fn get_devices(sidecar: State<'_, SidecarManager>) -> Result<serde_json::Value, String> {
    sidecar.send_command("get_devices", serde_json::json!({})).await
}

#[tauri::command]
async fn refresh_devices(sidecar: State<'_, SidecarManager>) -> Result<serde_json::Value, String> {
    sidecar.send_command("refresh_devices", serde_json::json!({})).await
}

#[tauri::command]
async fn set_default_device(sidecar: State<'_, SidecarManager>, id: String) -> Result<(), String> {
    sidecar
        .send_command("set_default_device", serde_json::json!({"id": id}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn rename_device(
    sidecar: State<'_, SidecarManager>,
    id: String,
    name: String,
) -> Result<(), String> {
    sidecar
        .send_command("rename_device", serde_json::json!({"id": id, "name": name}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn remove_device(sidecar: State<'_, SidecarManager>, id: String) -> Result<(), String> {
    sidecar
        .send_command("remove_device", serde_json::json!({"id": id}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn hide_device(sidecar: State<'_, SidecarManager>, id: String) -> Result<(), String> {
    sidecar
        .send_command("hide_device", serde_json::json!({"id": id}))
        .await?;
    Ok(())
}

// ── Media parsing ──
// Frontend has two separate commands; Python has one `parse_media` with type param.

#[tauri::command]
async fn parse_media_file(
    sidecar: State<'_, SidecarManager>,
    file_path: String,
) -> Result<serde_json::Value, String> {
    sidecar
        .send_command(
            "parse_media",
            serde_json::json!({"type": "file", "path": file_path}),
        )
        .await
}

#[tauri::command]
async fn parse_media_url(
    sidecar: State<'_, SidecarManager>,
    url: String,
) -> Result<serde_json::Value, String> {
    sidecar
        .send_command(
            "parse_media",
            serde_json::json!({"type": "url", "url": url}),
        )
        .await
}

#[tauri::command]
async fn resolve_bilibili(
    sidecar: State<'_, SidecarManager>,
    url: String,
) -> Result<serde_json::Value, String> {
    sidecar
        .send_command("resolve_bilibili", serde_json::json!({"url": url}))
        .await
}

// ── Cast control ──

#[tauri::command]
async fn start_cast(
    sidecar: State<'_, SidecarManager>,
    device_id: String,
    media_uri: String,
) -> Result<(), String> {
    sidecar
        .send_command(
            "start_cast",
            serde_json::json!({"device_id": device_id, "media_uri": media_uri}),
        )
        .await?;
    Ok(())
}

#[tauri::command]
async fn stop_cast(
    sidecar: State<'_, SidecarManager>,
    device_id: Option<String>,
) -> Result<(), String> {
    sidecar
        .send_command("stop_cast", serde_json::json!({"device_id": device_id}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn pause_cast(
    sidecar: State<'_, SidecarManager>,
    device_id: Option<String>,
) -> Result<(), String> {
    sidecar
        .send_command("pause_cast", serde_json::json!({"device_id": device_id}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn resume_cast(
    sidecar: State<'_, SidecarManager>,
    device_id: Option<String>,
) -> Result<(), String> {
    sidecar
        .send_command("resume_cast", serde_json::json!({"device_id": device_id}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn seek_cast(
    sidecar: State<'_, SidecarManager>,
    position: String,
    device_id: Option<String>,
) -> Result<(), String> {
    sidecar
        .send_command(
            "seek_cast",
            serde_json::json!({"position": position, "device_id": device_id}),
        )
        .await?;
    Ok(())
}

#[tauri::command]
async fn get_cast_state(
    sidecar: State<'_, SidecarManager>,
    device_id: Option<String>,
) -> Result<serde_json::Value, String> {
    sidecar
        .send_command("get_cast_state", serde_json::json!({"device_id": device_id}))
        .await
}

#[tauri::command]
async fn get_cast_url(
    sidecar: State<'_, SidecarManager>,
    device_id: Option<String>,
) -> Result<serde_json::Value, String> {
    sidecar
        .send_command("get_cast_url", serde_json::json!({"device_id": device_id}))
        .await
}

#[tauri::command]
async fn set_volume(
    sidecar: State<'_, SidecarManager>,
    volume: u32,
    device_id: Option<String>,
) -> Result<u32, String> {
    let result = sidecar
        .send_command(
            "set_volume",
            serde_json::json!({"volume": volume, "device_id": device_id}),
        )
        .await?;
    Ok(result.as_u64().unwrap_or(volume as u64) as u32)
}

#[tauri::command]
async fn set_mute(
    sidecar: State<'_, SidecarManager>,
    muted: bool,
    device_id: Option<String>,
) -> Result<(), String> {
    sidecar
        .send_command(
            "set_mute",
            serde_json::json!({"muted": muted, "device_id": device_id}),
        )
        .await?;
    Ok(())
}

// ── Settings ──

#[tauri::command]
async fn get_settings(sidecar: State<'_, SidecarManager>) -> Result<serde_json::Value, String> {
    sidecar.send_command("get_settings", serde_json::json!({})).await
}

#[tauri::command]
async fn save_settings(
    sidecar: State<'_, SidecarManager>,
    settings: serde_json::Value,
) -> Result<(), String> {
    sidecar
        .send_command("save_settings", serde_json::json!({"settings": settings}))
        .await?;
    Ok(())
}

// ── Update Check ──

#[tauri::command]
async fn check_update(
    sidecar: State<'_, SidecarManager>,
    current_version: String,
    force: Option<bool>,
) -> Result<serde_json::Value, String> {
    sidecar
        .send_command(
            "check_update",
            serde_json::json!({
                "current_version": current_version,
                "sources": ["github", "gitee"],
                "force": force.unwrap_or(false),
            }),
        )
        .await
}

#[tauri::command]
async fn ignore_update_version(
    sidecar: State<'_, SidecarManager>,
    version: String,
) -> Result<bool, String> {
    let result = sidecar
        .send_command("ignore_update_version", serde_json::json!({"version": version}))
        .await?;
    Ok(result.as_bool().unwrap_or(false))
}

// ── Device Guard (投屏确认) ──

#[tauri::command]
async fn respond_cast_confirm(
    sidecar: State<'_, SidecarManager>,
    request_id: String,
    approved: bool,
    policy: String,
) -> Result<bool, String> {
    let result = sidecar
        .send_command(
            "respond_cast_confirm",
            serde_json::json!({"request_id": request_id, "approved": approved, "policy": policy}),
        )
        .await?;
    Ok(result.as_bool().unwrap_or(false))
}

#[tauri::command]
async fn get_guard_devices(sidecar: State<'_, SidecarManager>) -> Result<serde_json::Value, String> {
    sidecar
        .send_command("get_guard_devices", serde_json::json!({}))
        .await
}

#[tauri::command]
async fn remove_guard_device(
    sidecar: State<'_, SidecarManager>,
    device_key: String,
) -> Result<bool, String> {
    let result = sidecar
        .send_command(
            "remove_guard_device",
            serde_json::json!({"device_key": device_key}),
        )
        .await?;
    Ok(result.as_bool().unwrap_or(false))
}

#[tauri::command]
async fn set_guard_policy(
    sidecar: State<'_, SidecarManager>,
    device_key: String,
    policy: String,
) -> Result<bool, String> {
    let result = sidecar
        .send_command(
            "set_guard_policy",
            serde_json::json!({"device_key": device_key, "policy": policy}),
        )
        .await?;
    Ok(result.as_bool().unwrap_or(false))
}

#[tauri::command]
async fn get_guard_settings(sidecar: State<'_, SidecarManager>) -> Result<serde_json::Value, String> {
    sidecar
        .send_command("get_guard_settings", serde_json::json!({}))
        .await
}

#[tauri::command]
async fn save_guard_settings(
    sidecar: State<'_, SidecarManager>,
    settings: serde_json::Value,
) -> Result<(), String> {
    sidecar
        .send_command("save_guard_settings", settings)
        .await?;
    Ok(())
}

// ── Microsoft Store Detection ──

#[tauri::command]
fn is_store_version() -> bool {
    let exe_path = std::env::current_exe().ok();
    if let Some(path) = exe_path {
        let path_str = path.to_string_lossy().to_lowercase();
        // 检测条件：
        // 1. 路径包含 "windowsapps"（微软商店标准路径）
        // 2. 路径包含 "553787e6.hancast"（MSIX Identity Name）
        // 3. 路径包含 "build-msix"（本地 MSIX 注册安装）
        return path_str.contains("windowsapps")
            || path_str.contains("553787e6.hancast")
            || path_str.contains("build-msix");
    }
    false
}

// ── MPV Management ──

#[tauri::command]
async fn check_mpv(sidecar: State<'_, SidecarManager>) -> Result<serde_json::Value, String> {
    sidecar.send_command("check_mpv", serde_json::json!({})).await
}

#[tauri::command]
async fn set_mpv_path(
    sidecar: State<'_, SidecarManager>,
    path: String,
) -> Result<serde_json::Value, String> {
    sidecar
        .send_command("set_mpv_path", serde_json::json!({"path": path}))
        .await
}

// ── Export Logs ──

#[tauri::command]
async fn export_logs(app: tauri::AppHandle) -> Result<bool, String> {
    use tauri_plugin_dialog::DialogExt;

    // 获取日志文件路径（跨平台，与 Python 后端 logger.py 一致）
    let log_path = if cfg!(target_os = "windows") {
        // Windows: %APPDATA%/HanCast/logs/hancast.log
        let app_data = std::env::var("APPDATA")
            .map_err(|_| "无法获取 APPDATA 目录".to_string())?;
        PathBuf::from(app_data).join("HanCast").join("logs").join("hancast.log")
    } else if cfg!(target_os = "macos") {
        // macOS: ~/Library/Application Support/HanCast/logs/hancast.log
        let home = std::env::var("HOME")
            .map_err(|_| "无法获取 HOME 目录".to_string())?;
        PathBuf::from(home).join("Library").join("Application Support").join("HanCast").join("logs").join("hancast.log")
    } else {
        // Linux: ~/.config/hancast/logs/hancast.log
        let home = std::env::var("HOME")
            .map_err(|_| "无法获取 HOME 目录".to_string())?;
        PathBuf::from(home).join(".config").join("hancast").join("logs").join("hancast.log")
    };

    // Rust 侧会话日志（启动、网络授权、防火墙、自启等）与 Python 日志
    // 不在同一目录，导出时合并到同一个文件，避免用户只拿到半份日志。
    let rust_log_path = app
        .path()
        .app_data_dir()
        .map(|dir| dir.join("logs").join("hancast.log"))
        .ok()
        .filter(|p| p.exists());

    if !log_path.exists() && rust_log_path.is_none() {
        return Err("日志文件不存在".to_string());
    }

    // 打开文件保存对话框
    let file_path = app
        .dialog()
        .file()
        .set_title("导出日志")
        .set_file_name("hancast.log")
        .add_filter("日志文件", &["log"])
        .add_filter("所有文件", &["*"])
        .blocking_save_file();

    match file_path {
        Some(path) => {
            let path_buf = path.into_path().map_err(|e| format!("Invalid path: {e}"))?;

            let read_log = |p: &std::path::Path| -> String {
                std::fs::read(p)
                    .map(|bytes| String::from_utf8_lossy(&bytes).into_owned())
                    .unwrap_or_default()
            };

            let mut content = String::new();
            if let Some(rust_path) = &rust_log_path {
                content.push_str("===== HanCast (Rust) =====\n");
                content.push_str(&read_log(rust_path));
                content.push_str("\n\n");
            }
            if log_path.exists() {
                content.push_str("===== HanCast Sidecar (Python) =====\n");
                content.push_str(&read_log(&log_path));
            }

            std::fs::write(&path_buf, content.as_bytes())
                .map_err(|e| format!("写入日志文件失败: {e}"))?;
            Ok(true)
        }
        None => Ok(false), // 用户取消了对话框
    }
}

/// 托盘菜单项：复制当前投屏地址（固定文本，有 URL 时可点击）
const CAST_URL_LABEL: &str = "复制当前投屏地址";

/// 托盘菜单里显示的投屏协议（只读，切换只在设置页进行）
fn protocol_menu_label(protocol: &str) -> String {
    match protocol {
        "dlna" => "投屏协议：DLNA".to_string(),
        "nva" => "投屏协议：哔哩必连".to_string(),
        _ => "投屏协议：—".to_string(),
    }
}

// ── Autostart ──
// 平台分叉收在 platform_autostart 模块：Windows MSIX 走 WinRT，其余走插件。

async fn get_autostart_state(app: &tauri::AppHandle) -> bool {
    platform_autostart::get_state(app).await.unwrap_or(false)
}

#[tauri::command]
async fn get_autostart(app: tauri::AppHandle) -> Result<bool, String> {
    platform_autostart::get_state(&app).await
}

/// 写入开机自启并记录诊断信息（设置页与托盘菜单共用）。
async fn apply_autostart(app: &tauri::AppHandle, enabled: bool) -> Result<(), String> {
    let outcome = platform_autostart::set_state(app, enabled).await;

    // LaunchAgent 的写入结果与参数是排查“登录不启动”的关键
    if let Some(logger) = app.try_state::<SessionLogger>() {
        match &outcome {
            Ok(()) => {
                logger.log(&format!(
                    "开机自启已{}",
                    if enabled { "启用" } else { "禁用" }
                ));
                #[cfg(target_os = "macos")]
                logger.log(&platform_autostart::launch_agent_info(
                    &app.package_info().name,
                ));
            }
            Err(e) => logger.log(&format!("设置开机自启失败: {e}")),
        }
    }

    outcome
}

#[tauri::command]
async fn set_autostart(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    apply_autostart(&app, enabled).await?;
    // 通知托盘菜单同步 CheckMenuItem 状态
    let _ = app.emit("autostart-changed", enabled);
    Ok(())
}

/// macOS 应用菜单。
///
/// Tauri 默认菜单是英文标签，且没有 About 元数据定制；这里显式构建，
/// 与托盘菜单一起保证「关于 / 隐藏 / 退出」完整，并保留编辑菜单的
/// Cmd+C/V 等标准快捷键。`quit` 走 NSApp terminate → `ExitRequested`，
/// 复用统一的 sidecar/MPV 清理流程（Cmd+Q 语义不变）。
#[cfg(target_os = "macos")]
fn setup_macos_menu(app: &tauri::App) -> tauri::Result<()> {
    let pkg = app.package_info();
    let about = AboutMetadata {
        name: Some(pkg.name.clone()),
        version: Some(pkg.version.to_string()),
        copyright: Some("GPL-3.0 · 基于 xfangfang/Macast 的二次开发".to_string()),
        credits: Some("https://github.com/lanzeweie/HanCast".to_string()),
        ..Default::default()
    };

    // ── 应用菜单 ──
    let about_item = PredefinedMenuItem::about(app, Some("关于 HanCast"), Some(about))?;
    let app_sep1 = PredefinedMenuItem::separator(app)?;
    let services = PredefinedMenuItem::services(app, Some("服务"))?;
    let app_sep2 = PredefinedMenuItem::separator(app)?;
    let hide = PredefinedMenuItem::hide(app, Some("隐藏 HanCast"))?;
    let hide_others = PredefinedMenuItem::hide_others(app, Some("隐藏其他"))?;
    let show_all = PredefinedMenuItem::show_all(app, Some("显示全部"))?;
    let app_sep3 = PredefinedMenuItem::separator(app)?;
    let quit = PredefinedMenuItem::quit(app, Some("退出 HanCast"))?;

    let app_menu = Submenu::with_items(
        app,
        "HanCast",
        true,
        &[
            &about_item,
            &app_sep1,
            &services,
            &app_sep2,
            &hide,
            &hide_others,
            &show_all,
            &app_sep3,
            &quit,
        ],
    )?;

    // ── 编辑菜单（文本输入框依赖这些标准快捷键）──
    let undo = PredefinedMenuItem::undo(app, Some("撤销"))?;
    let redo = PredefinedMenuItem::redo(app, Some("重做"))?;
    let edit_sep1 = PredefinedMenuItem::separator(app)?;
    let cut = PredefinedMenuItem::cut(app, Some("剪切"))?;
    let copy = PredefinedMenuItem::copy(app, Some("复制"))?;
    let paste = PredefinedMenuItem::paste(app, Some("粘贴"))?;
    let select_all = PredefinedMenuItem::select_all(app, Some("全选"))?;

    let edit_menu = Submenu::with_items(
        app,
        "编辑",
        true,
        &[&undo, &redo, &edit_sep1, &cut, &copy, &paste, &select_all],
    )?;

    // ── 显示菜单 ──
    let fullscreen = PredefinedMenuItem::fullscreen(app, Some("进入全屏幕"))?;
    let view_menu = Submenu::with_items(app, "显示", true, &[&fullscreen])?;

    // ── 窗口菜单（WINDOW_SUBMENU_ID 让 AppKit 识别为标准窗口菜单）──
    let minimize = PredefinedMenuItem::minimize(app, Some("最小化"))?;
    let zoom = PredefinedMenuItem::maximize(app, Some("缩放"))?;
    let window_sep1 = PredefinedMenuItem::separator(app)?;
    let bring_all = PredefinedMenuItem::bring_all_to_front(app, Some("前置全部窗口"))?;
    let window_sep2 = PredefinedMenuItem::separator(app)?;
    let close = PredefinedMenuItem::close_window(app, Some("关闭窗口"))?;

    let window_menu = Submenu::with_id_and_items(
        app,
        tauri::menu::WINDOW_SUBMENU_ID,
        "窗口",
        true,
        &[&minimize, &zoom, &window_sep1, &bring_all, &window_sep2, &close],
    )?;

    let menu = AppMenu::with_items(app, &[&app_menu, &edit_menu, &view_menu, &window_menu])?;
    app.set_menu(menu)?;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_autostart::init(
            tauri_plugin_autostart::MacosLauncher::LaunchAgent,
            Some(vec!["--minimized"]),
        ))
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            // 当第二个实例启动时，聚焦到已运行的窗口
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.show();
                let _ = window.set_focus();
            }
        }))
        .on_menu_event(|app, event| {
            if event.id() == "show" {
                if let Some(window) = app.get_webview_window("main") {
                    window.show().ok();
                    window.set_focus().ok();
                }
            } else if event.id() == "copy_cast_url" {
                // 从状态中读取完整 URL 并复制到剪贴板
                if let Some(state) = app.try_state::<CastUrlState>() {
                    let url = state.url.lock().unwrap().clone();
                    if !url.is_empty() {
                        app.clipboard().write_text(url).ok();
                    }
                }
            } else if event.id() == "quit" {
                // 统一走 RunEvent::ExitRequested：先清理 sidecar（连带 MPV），再退出
                app.exit(0);
            } else if event.id() == "autostart" {
                // CheckMenuItem 已自动切换 checked 状态，执行实际操作
                let app_handle = app.clone();
                tauri::async_runtime::spawn(async move {
                    let current = get_autostart_state(&app_handle).await;
                    if let Err(e) = apply_autostart(&app_handle, !current).await {
                        eprintln!("[Autostart] 切换失败: {e}");
                    }
                    // 通知前端同步状态
                    let enabled = get_autostart_state(&app_handle).await;
                    let _ = app_handle.emit("autostart-changed", enabled);
                });
            }
        })
        .setup(|app| {
            // 初始化会话日志（每次启动清空旧日志）
            let log_dir = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join("logs");
            let logger = SessionLogger::new(&log_dir);
            logger.log("=== HanCast 启动 ===");

            // macOS：显式应用菜单（关于 / 隐藏 / 退出 + 编辑 / 窗口）
            #[cfg(target_os = "macos")]
            setup_macos_menu(app)?;

            // macOS：主进程先触发本地网络授权（弹窗归属到 HanCast），
            // 再启动 Python sidecar，否则 sidecar 的 SSDP 发送会被静默拒绝
            #[cfg(target_os = "macos")]
            warm_up_local_network(&logger);

            // macOS：记录应用防火墙状态，便于排查「手机搜不到 / 8080 不可达」
            #[cfg(target_os = "macos")]
            log_firewall_status(&logger);

            app.manage(logger);

            // 加载窗口配置
            let config_path = app
                .path()
                .app_data_dir()
                .unwrap_or_else(|_| PathBuf::from("."))
                .join("window_config.json");

            let window_config_state = WindowConfigState::load(&config_path);

            // 开发模式下自动打开 DevTools
            #[cfg(debug_assertions)]
            if let Some(window) = app.get_webview_window("main") {
                window.open_devtools();
            }

            // 开机自启检测（必须在窗口显示之前）
            // 非 MSIX: 通过 --minimized 参数检测（tauri-plugin-autostart 通过注册表传递）
            // MSIX: 通过 --autostart 参数检测（uap10:Parameters 在 AppxManifest.xml 中配置）
            let should_start_minimized = std::env::args().any(|a| a == "--autostart" || a == "--minimized");

            if should_start_minimized {
                eprintln!("[Startup] 检测到启动参数，最小化到托盘");
                app.state::<SessionLogger>().log(
                    "检测到 --minimized/--autostart：窗口保持隐藏，仅显示托盘/菜单栏图标",
                );
            }

            // 恢复窗口尺寸（窗口默认隐藏，设置好后再显示，避免闪烁）
            let mut window_size_msg: Option<String> = None;
            if let Some(window) = app.get_webview_window("main") {
                let config = window_config_state.get_config();

                // 最小尺寸保护（防止配置丢失时窗口变成 1x1）
                const MIN_WIDTH: u32 = 346;
                const MIN_HEIGHT: u32 = 472;
                // 配置按逻辑尺寸（CSS px）保存：Windows 上 1:1，macOS 2x 屏上
                // 用 PhysicalSize 会把窗口缩成一半，导致内容被裁切
                let width = config.width.max(MIN_WIDTH as f64);
                let height = config.height.max(MIN_HEIGHT as f64);

                // 设置窗口尺寸
                let _ = window.set_size(tauri::Size::Logical(tauri::LogicalSize {
                    width,
                    height,
                }));

                // 打印窗口尺寸（启动时一次性记录）
                let msg = format!("窗口逻辑尺寸: {width}x{height} (config: {}x{}, min: {}x{})", config.width, config.height, MIN_WIDTH, MIN_HEIGHT);
                let logger = app.state::<SessionLogger>();
                logger.log(&msg);
                window_size_msg = Some(msg);

                // 禁用最大化（阻止双击标题栏最大化）
                window.set_maximizable(false).ok();

                // 监听窗口事件
                let window_config_clone = window_config_state.clone();
                let window_for_events = window.clone();
                let app_handle_for_close = app.handle().clone();
                window.on_window_event(move |event| {
                    match event {
                        tauri::WindowEvent::Resized(size) => {
                            let mut config = window_config_clone.get_config();
                            // Resized 给的是物理像素；按当前缩放比换算回逻辑尺寸，
                            // 保证在 Retina / 多显示器之间切换时大小稳定
                            let scale = window_for_events.scale_factor().unwrap_or(1.0);
                            config.width = (size.width as f64 / scale).max(MIN_WIDTH as f64);
                            config.height = (size.height as f64 / scale).max(MIN_HEIGHT as f64);
                            window_config_clone.update_and_save(config);
                        }
                        // 拦截关闭请求，隐藏到托盘而不是真正关闭
                        tauri::WindowEvent::CloseRequested { api, .. } => {
                            // 阻止默认关闭行为
                            api.prevent_close();
                            // 隐藏窗口到托盘
                            if let Some(window) = app_handle_for_close.get_webview_window("main") {
                                window.hide().ok();
                            }
                        }
                        _ => {}
                    }
                });

                // 根据启动参数决定是否显示窗口
                if !should_start_minimized {
                    let _ = window.show();
                    let _ = window.set_focus();
                }
            }

            app.manage(window_config_state);

            // Initialize Python sidecar
            let sidecar = SidecarManager::new(app.handle().clone())?;
            app.manage(sidecar);

            // 同步启动窗口尺寸到 sidecar 日志（导出的日志中可见）
            if let Some(msg) = window_size_msg {
                let handle = app.handle().clone();
                tauri::async_runtime::spawn(async move {
                    let sidecar = handle.state::<SidecarManager>();
                    let _ = sidecar.send_command("log", serde_json::json!({"msg": msg})).await;
                });
            }

            // Initialize cast URL state
            let cast_url = Arc::new(Mutex::new(String::new()));
            app.manage(CastUrlState {
                url: cast_url.clone(),
            });

            // Build tray menu
            let protocol_item = MenuItemBuilder::with_id("protocol", protocol_menu_label(""))
                .enabled(false)
                .build(app)?;
            let cast_url_item = MenuItemBuilder::with_id("copy_cast_url", CAST_URL_LABEL)
                .enabled(false)
                .build(app)?;
            let show = MenuItemBuilder::with_id("show", "显示窗口")
                .build(app)?;
            let autostart_item = CheckMenuItemBuilder::with_id("autostart", "开机自启")
                .checked(tauri::async_runtime::block_on(get_autostart_state(app.handle())))
                .build(app)?;
            let quit = MenuItemBuilder::with_id("quit", "退出")
                .build(app)?;
            let menu = MenuBuilder::new(app)
                .item(&protocol_item)
                .item(&cast_url_item)
                .item(&show)
                .item(&autostart_item)
                .item(&quit)
                .build()?;

            // Build tray icon (禁用左键弹出菜单，左键只显示窗口)
            // macOS 菜单栏需要单色模板图（44px 源图由 tray-icon 缩放到 18pt）；
            // 彩色应用图标在菜单栏会显得突兀，其他平台保持原样
            #[cfg(target_os = "macos")]
            let tray_icon = tauri::image::Image::from_bytes(include_bytes!(
                "../icons/trayTemplate.png"
            ))
            .expect("failed to load tray template icon");
            #[cfg(not(target_os = "macos"))]
            let tray_icon = app.default_window_icon().unwrap().clone();

            let mut tray_builder = TrayIconBuilder::new()
                .icon(tray_icon)
                .tooltip(format!("HanCast v{}", env!("CARGO_PKG_VERSION")))
                .menu(&menu)
                .show_menu_on_left_click(false)
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            // 始终先 show + unminimize，再 set_focus，确保各平台行为一致
                            let _ = window.show();
                            let _ = window.unminimize();
                            let _ = window.set_focus();
                        }
                    }
                });

            #[cfg(target_os = "macos")]
            {
                tray_builder = tray_builder.icon_as_template(true);
            }

            let tray = tray_builder.build(app)?;

            // Background task: startup update check (non-blocking, 2s timeout)
            let app_handle_update = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                // 微软商店版本由 Store 自动管理更新，跳过检查
                if is_store_version() {
                    eprintln!("[Update] Microsoft Store version — skipping auto-update check");
                    return;
                }

                // 等待 sidecar 就绪
                tokio::time::sleep(std::time::Duration::from_secs(3)).await;

                let current_version = app_handle_update
                    .config()
                    .version
                    .clone()
                    .unwrap_or_else(|| "0.0.0".to_string());

                let sidecar = app_handle_update.state::<SidecarManager>();
                match sidecar
                    .send_command(
                        "check_update",
                        serde_json::json!({"current_version": current_version, "sources": ["github"]}),
                    )
                    .await
                {
                    Ok(result) => {
                        if result.get("has_update").and_then(|v| v.as_bool()).unwrap_or(false) {
                            let _ = app_handle_update.emit("update-available", &result);
                            eprintln!(
                                "[Update] New version available: {} → {}",
                                current_version,
                                result.get("latest").and_then(|v| v.as_str()).unwrap_or("?")
                            );
                        }
                    }
                    Err(e) => {
                        eprintln!("[Update] Startup check failed: {e}");
                    }
                }
            });

            // Background task: poll get_cast_url every second and update tray menu
            let app_handle = app.handle().clone();
            let tray_id = tray.id().clone();
            tauri::async_runtime::spawn(async move {
                let mut last_url = String::new();
                let mut last_autostart = get_autostart_state(&app_handle).await;
                let mut last_protocol = String::new();
                loop {
                    tokio::time::sleep(std::time::Duration::from_secs(1)).await;

                    // 一次 IPC 同时取 URL 与协议，避免每秒两条 stdin/stdout 往返
                    let sidecar = app_handle.state::<SidecarManager>();
                    let snapshot = sidecar
                        .send_command("get_cast_url", serde_json::json!({}))
                        .await
                        .unwrap_or(serde_json::Value::Null);
                    let new_url = snapshot
                        .get("url")
                        .and_then(|v| v.as_str())
                        .unwrap_or("")
                        .to_string();
                    // 协议只用于托盘显示，切换在设置页触发；取不到时沿用上一次的值
                    let cur_protocol = snapshot
                        .get("protocol")
                        .and_then(|v| v.as_str())
                        .map(str::to_string)
                        .unwrap_or_else(|| last_protocol.clone());

                    let cur_autostart = get_autostart_state(&app_handle).await;
                    let url_changed = new_url != last_url;
                    let autostart_changed = cur_autostart != last_autostart;
                    let protocol_changed = cur_protocol != last_protocol;

                    // Only update menu when something changed
                    if url_changed || autostart_changed || protocol_changed {
                        last_url = new_url.clone();
                        last_autostart = cur_autostart;
                        last_protocol = cur_protocol.clone();
                        // Update state for clipboard copy
                        if let Some(state) = app_handle.try_state::<CastUrlState>() {
                            *state.url.lock().unwrap() = new_url.clone();
                        }
                        // Update tray menu item label
                        if let Some(tray) = app_handle.tray_by_id(&tray_id) {
                            let protocol_item = MenuItemBuilder::with_id(
                                "protocol",
                                protocol_menu_label(&cur_protocol),
                            )
                            .enabled(false)
                            .build(&app_handle)
                            .unwrap();
                            let new_item = MenuItemBuilder::with_id(
                                "copy_cast_url",
                                CAST_URL_LABEL,
                            )
                            .enabled(!new_url.is_empty())
                            .build(&app_handle)
                            .unwrap();
                            let show_item = MenuItemBuilder::with_id("show", "显示窗口")
                                .build(&app_handle)
                                .unwrap();
                            let autostart_item = CheckMenuItemBuilder::with_id(
                                "autostart",
                                "开机自启",
                            )
                            .checked(cur_autostart)
                            .build(&app_handle)
                            .unwrap();
                            let quit_item = MenuItemBuilder::with_id("quit", "退出")
                                .build(&app_handle)
                                .unwrap();
                            let new_menu = MenuBuilder::new(&app_handle)
                                .item(&protocol_item)
                                .item(&new_item)
                                .item(&show_item)
                                .item(&autostart_item)
                                .item(&quit_item)
                                .build()
                                .unwrap();
                            tray.set_menu(Some(new_menu)).ok();
                        }
                    }
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            minimize_window,
            close_window,
            get_devices,
            refresh_devices,
            set_default_device,
            rename_device,
            remove_device,
            hide_device,
            parse_media_file,
            parse_media_url,
            resolve_bilibili,
            start_cast,
            stop_cast,
            pause_cast,
            resume_cast,
            seek_cast,
            get_cast_state,
            get_cast_url,
            set_volume,
            set_mute,
            get_settings,
            save_settings,
            check_update,
            ignore_update_version,
            respond_cast_confirm,
            get_guard_devices,
            remove_guard_device,
            set_guard_policy,
            get_guard_settings,
            save_guard_settings,
            check_mpv,
            set_mpv_path,
            export_logs,
            is_store_version,
            get_autostart,
            set_autostart,
            get_firewall_status,
            open_firewall_settings,
        ])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    // 统一退出/重开入口：
    // - ExitRequested：Cmd+Q、托盘“退出”、关闭最后一个窗口都会经过这里。
    //   macOS 没有 Job Object，必须先等 sidecar 结束（它负责退出 MPV），
    //   否则 MPV 会变成孤儿进程留在后台。
    // - Reopen：点击 Dock 图标时把隐藏到托盘的窗口重新显示出来。
    app.run(|app_handle, event| match event {
        #[cfg(target_os = "macos")]
        tauri::RunEvent::Reopen {
            has_visible_windows,
            ..
        } => {
            if !has_visible_windows {
                if let Some(window) = app_handle.get_webview_window("main") {
                    let _ = window.show();
                    let _ = window.unminimize();
                    let _ = window.set_focus();
                }
            }
        }
        tauri::RunEvent::ExitRequested { api, .. } => {
            match EXIT_STATE.load(Ordering::SeqCst) {
                // 清理已完成，这是我们自己调用 exit() 触发的请求，放行
                EXIT_READY => return,
                // 清理进行中（用户重复按 Cmd+Q），继续拦下
                EXIT_CLEANING => {
                    api.prevent_exit();
                    return;
                }
                _ => {}
            }

            EXIT_STATE.store(EXIT_CLEANING, Ordering::SeqCst);
            api.prevent_exit();
            let handle = app_handle.clone();
            tauri::async_runtime::spawn(async move {
                handle.state::<SidecarManager>().shutdown().await;
                EXIT_STATE.store(EXIT_READY, Ordering::SeqCst);
                handle.exit(0);
            });
        }
        _ => {}
    });
}
