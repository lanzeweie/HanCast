mod sidecar;

use sidecar::SidecarManager;
use tauri::{
    menu::{MenuBuilder, MenuItemBuilder},
    tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent},
    Manager, State,
};

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
async fn stop_cast(sidecar: State<'_, SidecarManager>) -> Result<(), String> {
    sidecar
        .send_command("stop_cast", serde_json::json!({}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn pause_cast(sidecar: State<'_, SidecarManager>) -> Result<(), String> {
    sidecar
        .send_command("pause_cast", serde_json::json!({}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn resume_cast(sidecar: State<'_, SidecarManager>) -> Result<(), String> {
    sidecar
        .send_command("resume_cast", serde_json::json!({}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn seek_cast(sidecar: State<'_, SidecarManager>, position: String) -> Result<(), String> {
    sidecar
        .send_command("seek_cast", serde_json::json!({"position": position}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn get_cast_state(sidecar: State<'_, SidecarManager>) -> Result<serde_json::Value, String> {
    sidecar.send_command("get_cast_state", serde_json::json!({})).await
}

#[tauri::command]
async fn set_volume(sidecar: State<'_, SidecarManager>, volume: u32) -> Result<(), String> {
    sidecar
        .send_command("set_volume", serde_json::json!({"volume": volume}))
        .await?;
    Ok(())
}

#[tauri::command]
async fn set_mute(sidecar: State<'_, SidecarManager>, muted: bool) -> Result<(), String> {
    sidecar
        .send_command("set_mute", serde_json::json!({"muted": muted}))
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

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .on_menu_event(|app, event| {
            if event.id() == "show" {
                if let Some(window) = app.get_webview_window("main") {
                    window.show().ok();
                    window.set_focus().ok();
                }
            } else if event.id() == "quit" {
                app.exit(0);
            }
        })
        .setup(|app| {
            // Initialize Python sidecar
            let sidecar = SidecarManager::new(app.handle().clone())?;
            app.manage(sidecar);

            // Build tray menu
            let show = MenuItemBuilder::with_id("show", "显示窗口")
                .build(app)
                .unwrap();
            let quit = MenuItemBuilder::with_id("quit", "退出")
                .build(app)
                .unwrap();
            let menu = MenuBuilder::new(app).item(&show).item(&quit).build().unwrap();

            // Build tray icon
            let _tray = TrayIconBuilder::new()
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
            parse_media_file,
            parse_media_url,
            start_cast,
            stop_cast,
            pause_cast,
            resume_cast,
            seek_cast,
            get_cast_state,
            set_volume,
            set_mute,
            get_settings,
            save_settings,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
