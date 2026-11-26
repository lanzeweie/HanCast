//! 开机自启的统一入口。
//!
//! - Windows MSIX / Microsoft Store 安装：走 WinRT `StartupTask`，注册表插件会失效
//! - 其他情况（exe/NSIS 安装、macOS、Linux）：走 `tauri-plugin-autostart`
//!
//! 调用方只关心“读状态/写状态”，平台分叉全部收在这里。

use tauri::AppHandle;
use tauri_plugin_autostart::ManagerExt;

/// MSIX StartupTask ID（与 AppxManifest.xml 中的 TaskId 一致）
#[cfg(target_os = "windows")]
const STARTUP_TASK_ID: &str = "HanCastStartup";

#[cfg(target_os = "windows")]
mod msix {
    use super::STARTUP_TASK_ID;
    use windows::{
        core::HSTRING,
        ApplicationModel::{StartupTask, StartupTaskState},
    };

    pub async fn get_state() -> Result<bool, String> {
        let task_id = HSTRING::from(STARTUP_TASK_ID);
        let task = StartupTask::GetAsync(&task_id)
            .map_err(|e| format!("获取启动任务失败: {e}"))?
            .await
            .map_err(|e| format!("等待启动任务失败: {e}"))?;

        let state = task
            .State()
            .map_err(|e| format!("获取启动任务状态失败: {e}"))?;

        Ok(state == StartupTaskState::Enabled)
    }

    /// 参数通过 `uap10:Parameters="--autostart"` 在 AppxManifest.xml 中配置
    pub async fn set_state(enabled: bool) -> Result<(), String> {
        let task_id = HSTRING::from(STARTUP_TASK_ID);
        let task = StartupTask::GetAsync(&task_id)
            .map_err(|e| format!("获取启动任务失败: {e}"))?
            .await
            .map_err(|e| format!("等待启动任务失败: {e}"))?;

        if enabled {
            task.RequestEnableAsync()
                .map_err(|e| format!("请求启用启动任务失败: {e}"))?
                .await
                .map_err(|e| format!("等待启用结果失败: {e}"))?;
            eprintln!("[Autostart] MSIX 开机自启已启用");
        } else {
            task.Disable()
                .map_err(|e| format!("禁用启动任务失败: {e}"))?;
            eprintln!("[Autostart] MSIX 开机自启已禁用");
        }

        Ok(())
    }
}

/// 读取开机自启状态。
pub async fn get_state(app: &AppHandle) -> Result<bool, String> {
    #[cfg(target_os = "windows")]
    if crate::is_store_version() {
        return msix::get_state().await;
    }

    app.autolaunch().is_enabled().map_err(|e| e.to_string())
}

/// 设置开机自启状态。
pub async fn set_state(app: &AppHandle, enabled: bool) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    if crate::is_store_version() {
        return msix::set_state(enabled).await;
    }

    if enabled {
        app.autolaunch().enable().map_err(|e| e.to_string())
    } else {
        app.autolaunch().disable().map_err(|e| e.to_string())
    }
}

/// 返回 LaunchAgent plist 的诊断信息，写入会话日志。
///
/// `auto-launch` 的 macOS LaunchAgent plist 位于
/// `~/Library/LaunchAgents/{app_name}.plist`，ProgramArguments 里应同时包含
/// 可执行文件路径与 `--minimized`（由插件初始化参数传入）。
#[cfg(target_os = "macos")]
pub(crate) fn launch_agent_info(app_name: &str) -> String {
    let Some(path) = std::env::var_os("HOME").map(std::path::PathBuf::from).map(|home| {
        home.join("Library")
            .join("LaunchAgents")
            .join(format!("{app_name}.plist"))
    }) else {
        return "LaunchAgent: 无法确定 HOME 目录".to_string();
    };

    match std::fs::read_to_string(&path) {
        Ok(content) => format!(
            "LaunchAgent: {}（已写入，ProgramArguments {} --minimized）",
            path.display(),
            if content.contains("--minimized") {
                "包含"
            } else {
                "缺少"
            }
        ),
        Err(_) => format!("LaunchAgent: {}（未找到）", path.display()),
    }
}