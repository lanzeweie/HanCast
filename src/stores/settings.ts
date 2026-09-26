import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { AppSettings } from '@/types/settings'
import type { UnlistenFn } from '@tauri-apps/api/event'
import {
  getSettings,
  saveSettings as apiSaveSettings,
  getAutostart as apiGetAutostart,
  setAutostart as apiSetAutostart,
} from '@/api/commands'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<AppSettings>({
    usn: '',
    friendly_name: 'HanCast',
    version: '2.1.0',
    media_port: 8080,
    default_device: null,
    settings: {},
  })
  const loading = ref(false)
  const autostart = ref(false)

  let unlistenAutostart: UnlistenFn | null = null

  /** 监听 Rust 层 autostart-changed 事件（托盘菜单切换时触发） */
  async function initAutostartListener() {
    if (unlistenAutostart) return
    try {
      const { listen } = await import('@tauri-apps/api/event')
      unlistenAutostart = await listen<boolean>('autostart-changed', (event) => {
        autostart.value = event.payload
      })
    } catch {
      // Not in Tauri environment
    }
  }

  async function fetchSettings() {
    loading.value = true
    try {
      settings.value = await getSettings()
      autostart.value = await apiGetAutostart()
      initAutostartListener()
    } catch (err) {
      console.error('Failed to fetch settings:', err)
    } finally {
      loading.value = false
    }
  }

  async function saveSettings(patch: Partial<AppSettings>) {
    loading.value = true
    try {
      await apiSaveSettings(patch)
      settings.value = { ...settings.value, ...patch }
    } catch (err) {
      console.error('Failed to save settings:', err)
    } finally {
      loading.value = false
    }
  }

  async function toggleAutostart() {
    const newVal = !autostart.value
    try {
      await apiSetAutostart(newVal)
      autostart.value = newVal
    } catch (err) {
      console.error('Failed to toggle autostart:', err)
    }
  }

  return {
    settings,
    loading,
    autostart,
    fetchSettings,
    saveSettings,
    toggleAutostart,
  }
})
