import { ref } from 'vue'
import { defineStore } from 'pinia'
import type { AppSettings } from '@/types/settings'
import { getSettings, saveSettings as apiSaveSettings } from '@/api/commands'

export const useSettingsStore = defineStore('settings', () => {
  const settings = ref<AppSettings>({
    usn: '',
    friendly_name: 'Macast',
    version: '2.0.0',
    media_port: 8080,
    default_device: null,
    settings: {},
  })
  const loading = ref(false)

  async function fetchSettings() {
    loading.value = true
    try {
      settings.value = await getSettings()
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

  return {
    settings,
    loading,
    fetchSettings,
    saveSettings,
  }
})
