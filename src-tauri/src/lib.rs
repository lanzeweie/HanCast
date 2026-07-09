mod sidecar;

use sidecar::SidecarManager;
use std::sync::{Arc, Mutex};
use tauri::{
    menu::{CheckMenuItemBuilder, MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Emitter, Manager, State,
};
use tauri_plugin_autostart::ManagerExt;
use tauri_plugin_clipboard_manager::ClipboardExt;

/// 当前投屏 URL 缓存（供托盘菜单使用）
struct CastUrlState {
    url: Arc<Mutex<String>>,
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

/// 托盘菜单项：复制当前投屏地址（固定文本，有 URL 时可点击）
const CAST_URL_LABEL: &str = "复制当前投屏地址";

// ── Autostart ──

#[tauri::command]
fn get_autostart(app: tauri::AppHandle) -> Result<bool, String> {
    app.autolaunch()
        .is_enabled()
        .map_err(|e| e.to_string())
}

#[tauri::command]
fn set_autostart(app: tauri::AppHandle, enabled: bool) -> Result<(), String> {
    if enabled {
        app.autolaunch()
            .enable()
            .map_err(|e| e.to_string())?;
    } else {
        app.autolaunch()
            .disable()
            .map_err(|e| e.to_string())?;
    }
    // 通知托盘菜单同步 CheckMenuItem 状态
    let _ = app.emit("autostart-changed", enabled);
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
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
                app.exit(0);
            } else if event.id() == "autostart" {
                // CheckMenuItem 已自动切换 checked 状态，执行实际操作
                if app.autolaunch().is_enabled().unwrap_or(false) {
                    app.autolaunch().disable().ok();
                } else {
                    app.autolaunch().enable().ok();
                }
                // 通知前端同步状态
                let enabled = app.autolaunch().is_enabled().unwrap_or(false);
                let _ = app.emit("autostart-changed", enabled);
            }
        })
        .setup(|app| {
            // 开机自启时最小化到托盘（--minimized 参数由注册表/autostart 设置）
            if std::env::args().any(|a| a == "--minimized") {
                if let Some(window) = app.get_webview_window("main") {
                    window.hide().ok();
                }
            }

            // Initialize Python sidecar
            let sidecar = SidecarManager::new(app.handle().clone())?;
            app.manage(sidecar);

            // Initialize cast URL state
            let cast_url = Arc::new(Mutex::new(String::new()));
            app.manage(CastUrlState {
                url: cast_url.clone(),
            });

            // Build tray menu
            let cast_url_item = MenuItemBuilder::with_id("copy_cast_url", CAST_URL_LABEL)
                .enabled(false)
                .build(app)?;
            let show = MenuItemBuilder::with_id("show", "显示窗口")
                .build(app)?;
            let autostart_item = CheckMenuItemBuilder::with_id("autostart", "开机自启")
                .checked(app.autolaunch().is_enabled().unwrap_or(false))
                .build(app)?;
            let quit = MenuItemBuilder::with_id("quit", "退出")
                .build(app)?;
            let menu = MenuBuilder::new(app)
                .item(&cast_url_item)
                .item(&show)
                .item(&autostart_item)
                .item(&quit)
                .build()?;

            // Build tray icon
            let tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("HanCast")
                .menu(&menu)
                .on_tray_icon_event(|tray, event| {
                    if let TrayIconEvent::Click {
                        button: MouseButton::Left,
                        button_state: MouseButtonState::Up,
                        ..
                    } = event
                    {
                        let app = tray.app_handle();
                        if let Some(window) = app.get_webview_window("main") {
                            if window.is_visible().unwrap_or(false) {
                                window.hide().ok();
                            } else {
                                window.show().ok();
                                window.set_focus().ok();
                            }
                        }
                    }
                })
                .build(app)?;

            // Background task: startup update check (non-blocking, 2s timeout)
            let app_handle_update = app.handle().clone();
            tauri::async_runtime::spawn(async move {
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
                let mut last_autostart = app_handle.autolaunch().is_enabled().unwrap_or(false);
                loop {
                    tokio::time::sleep(std::time::Duration::from_secs(1)).await;

                    // Call sidecar to get current cast URL
                    let sidecar = app_handle.state::<SidecarManager>();
                    let new_url = match sidecar
                        .send_command("get_cast_url", serde_json::json!({}))
                        .await
                    {
                        Ok(val) => val
                            .get("url")
                            .and_then(|v| v.as_str())
                            .unwrap_or("")
                            .to_string(),
                        Err(_) => String::new(),
                    };

                    let cur_autostart = app_handle.autolaunch().is_enabled().unwrap_or(false);
                    let url_changed = new_url != last_url;
                    let autostart_changed = cur_autostart != last_autostart;

                    // Only update menu when something changed
                    if url_changed || autostart_changed {
                        last_url = new_url.clone();
                        last_autostart = cur_autostart;
                        // Update state for clipboard copy
                        if let Some(state) = app_handle.try_state::<CastUrlState>() {
                            *state.url.lock().unwrap() = new_url.clone();
                        }
                        // Update tray menu item label
                        if let Some(tray) = app_handle.tray_by_id(&tray_id) {
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
                            .checked(
                                app_handle
                                    .autolaunch()
                                    .is_enabled()
                                    .unwrap_or(false),
                            )
                            .build(&app_handle)
                            .unwrap();
                            let quit_item = MenuItemBuilder::with_id("quit", "退出")
                                .build(&app_handle)
                                .unwrap();
                            let new_menu = MenuBuilder::new(&app_handle)
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
            get_autostart,
            set_autostart,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
