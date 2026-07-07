mod sidecar;

use sidecar::SidecarManager;
use std::sync::{Arc, Mutex};
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, State,
};
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

/// 托盘菜单项：复制当前投屏地址（固定文本，有 URL 时可点击）
const CAST_URL_LABEL: &str = "复制当前投屏地址";

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_dialog::init())
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
            }
        })
        .setup(|app| {
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
            let quit = MenuItemBuilder::with_id("quit", "退出")
                .build(app)?;
            let menu = MenuBuilder::new(app)
                .item(&cast_url_item)
                .item(&show)
                .item(&quit)
                .build()?;

            // Build tray icon
            let tray = TrayIconBuilder::new()
                .icon(app.default_window_icon().unwrap().clone())
                .tooltip("Macast")
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

            // Background task: poll get_cast_url every second and update tray menu
            let app_handle = app.handle().clone();
            let tray_id = tray.id().clone();
            tauri::async_runtime::spawn(async move {
                let mut last_url = String::new();
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

                    // Only update menu when URL changed
                    if new_url != last_url {
                        last_url = new_url.clone();
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
                            let quit_item = MenuItemBuilder::with_id("quit", "退出")
                                .build(&app_handle)
                                .unwrap();
                            let new_menu = MenuBuilder::new(&app_handle)
                                .item(&new_item)
                                .item(&show_item)
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
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
