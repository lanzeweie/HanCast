import { ref, onMounted, onUnmounted } from 'vue'
import { defineStore } from 'pinia'
import type { Device } from '@/types/device'
import type { UnlistenFn } from '@tauri-apps/api/event'
import {
  getDevices,
  refreshDevices,
  setDefaultDevice as apiSetDefault,
  renameDevice as apiRename,
  hideDevice as apiHide,
} from '@/api/commands'

export const useDeviceStore = defineStore('device', () => {
  const devices = ref<Device[]>([])
  const selectedDevice = ref<Device | null>(null)
  const loading = ref(false)

  let refreshTimer: number | undefined
  const unlistenFns: UnlistenFn[] = []

  async function fetchDevices() {
    loading.value = true
    try {
      devices.value = await getDevices()
    } catch (err) {
      console.error('Failed to fetch devices:', err)
    } finally {
      loading.value = false
    }
  }

  async function refresh() {
    loading.value = true
    try {
      devices.value = await refreshDevices()
    } catch (err) {
      console.error('Failed to refresh devices:', err)
    } finally {
      loading.value = false
    }
  }

  async function setDefault(id: string) {
    await apiSetDefault(id)
    devices.value.forEach((d) => (d.is_default = d.id === id))
  }

  async function rename(id: string, name: string) {
    await apiRename(id, name)
    const device = devices.value.find((d) => d.id === id)
    if (device) device.name = name
  }

  async function hide(id: string) {
    await apiHide(id)
    devices.value = devices.value.filter((d) => d.id !== id)
    if (selectedDevice.value?.id === id) {
      selectedDevice.value = null
    }
  }

  function selectDevice(device: Device | null) {
    selectedDevice.value = device
  }

  // Set up event listeners
  async function setupListeners() {
    try {
      const { listen } = await import('@tauri-apps/api/event')

      // Device found
      unlistenFns.push(
        await listen<Device>('device_found', (event) => {
          const device = event.payload
          if (!devices.value.find((d) => d.id === device.id)) {
            devices.value.push(device)
          }
        })
      )

      // Device lost
      unlistenFns.push(
        await listen<{ id: string }>('device_lost', (event) => {
          devices.value = devices.value.filter((d) => d.id !== event.payload.id)
        })
      )
    } catch {
      // Running outside Tauri, skip listeners
    }
  }

  // Auto-refresh every 30s
  onMounted(() => {
    fetchDevices()
    setupListeners()
    refreshTimer = window.setInterval(fetchDevices, 30000)
  })

  onUnmounted(() => {
    if (refreshTimer) clearInterval(refreshTimer)
    unlistenFns.forEach((fn) => fn())
  })

  return {
    devices,
    selectedDevice,
    loading,
    fetchDevices,
    refresh,
    setDefault,
    rename,
    hide,
    selectDevice,
  }
})
