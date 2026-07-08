import { ref, onMounted, onUnmounted } from 'vue'
import { defineStore } from 'pinia'
import type { CastConfirmRequest, GuardDevice, GuardSettings } from '@/types/guard'
import type { UnlistenFn } from '@tauri-apps/api/event'
import {
  respondCastConfirm,
  getGuardDevices,
  removeGuardDevice as apiRemoveGuardDevice,
  setGuardPolicy as apiSetGuardPolicy,
  getGuardSettings,
  saveGuardSettings as apiSaveGuardSettings,
} from '@/api/commands'

export const useGuardStore = defineStore('guard', () => {
  // ── State ──
  const pendingRequest = ref<CastConfirmRequest | null>(null)
  const trustedDevices = ref<GuardDevice[]>([])
  const blacklistedDevices = ref<GuardDevice[]>([])
  const settings = ref<GuardSettings>({ enabled: true, confirm_timeout: 15 })
  const countdown = ref(0)
  const loading = ref(false)

  let countdownTimer: ReturnType<typeof setInterval> | null = null
  const unlistenFns: UnlistenFn[] = []
  let listenersSetup = false

  // ── Countdown ──
  function startCountdown() {
    stopCountdown()
    if (!pendingRequest.value) return

    countdown.value = pendingRequest.value.timeout
    countdownTimer = setInterval(() => {
      countdown.value--
      if (countdown.value <= 0) {
        // Auto-reject on timeout
        handleResponse(false, 'once')
      }
    }, 1000)
  }

  function stopCountdown() {
    if (countdownTimer) {
      clearInterval(countdownTimer)
      countdownTimer = null
    }
    countdown.value = 0
  }

  // ── Actions ──
  async function fetchDevices() {
    loading.value = true
    try {
      const result = await getGuardDevices()
      trustedDevices.value = result.trusted
      blacklistedDevices.value = result.blacklisted
    } catch (err) {
      console.error('Failed to fetch guard devices:', err)
    } finally {
      loading.value = false
    }
  }

  async function fetchSettings() {
    try {
      settings.value = await getGuardSettings()
    } catch (err) {
      console.error('Failed to fetch guard settings:', err)
    }
  }

  async function handleResponse(approved: boolean, policy: 'once' | 'always' | 'blacklist' | 'reject') {
    const request = pendingRequest.value
    if (!request) return

    stopCountdown()
    try {
      await respondCastConfirm(request.request_id, approved, policy)
    } catch (err) {
      console.error('Failed to respond cast confirm:', err)
    } finally {
      pendingRequest.value = null
      // Refresh device lists in case a new device was added
      fetchDevices()
    }
  }

  async function removeDevice(deviceKey: string) {
    try {
      await apiRemoveGuardDevice(deviceKey)
      trustedDevices.value = trustedDevices.value.filter((d) => d.udn !== deviceKey && d.ip !== deviceKey)
      blacklistedDevices.value = blacklistedDevices.value.filter((d) => d.udn !== deviceKey && d.ip !== deviceKey)
    } catch (err) {
      console.error('Failed to remove guard device:', err)
    }
  }

  async function setPolicy(deviceKey: string, policy: 'trusted' | 'blacklisted') {
    try {
      await apiSetGuardPolicy(deviceKey, policy)
      // Refresh lists to reflect changes
      fetchDevices()
    } catch (err) {
      console.error('Failed to set guard policy:', err)
    }
  }

  async function saveSettings(patch: { enabled?: boolean; confirm_timeout?: number }) {
    try {
      await apiSaveGuardSettings(patch)
      settings.value = { ...settings.value, ...patch }
    } catch (err) {
      console.error('Failed to save guard settings:', err)
    }
  }

  // ── Event listeners ──
  async function setupListeners() {
    if (listenersSetup) return
    listenersSetup = true
    try {
      const { listen } = await import('@tauri-apps/api/event')
      console.log('[Guard] Setting up cast_confirm_request listener')

      unlistenFns.push(
        await listen<CastConfirmRequest>('cast_confirm_request', (event) => {
          console.log('[Guard] Received cast_confirm_request:', event.payload)
          // If guard is disabled, auto-approve
          if (!settings.value.enabled) {
            respondCastConfirm(event.payload.request_id, true, 'once')
            return
          }
          // If there's already a pending request, reject the new one
          if (pendingRequest.value) {
            respondCastConfirm(event.payload.request_id, false, 'once')
            return
          }
          pendingRequest.value = event.payload
          startCountdown()

          // Try to bring window to focus
          import('@tauri-apps/api/window').then(({ getCurrentWindow }) => {
            const win = getCurrentWindow()
            win.show().then(() => win.setFocus()).catch(() => {})
          }).catch(() => {
            // Ignore — running outside Tauri or window API not available
          })
        }),
      )
      console.log('[Guard] Listener registered successfully')
    } catch (err) {
      console.error('[Guard] Failed to setup listeners:', err)
    }
  }

  onMounted(() => {
    console.log('[Guard] Store mounted, setting up listeners...')
    fetchDevices()
    fetchSettings()
    setupListeners()
  })

  onUnmounted(() => {
    stopCountdown()
    unlistenFns.forEach((fn) => fn())
  })

  // Also setup listeners immediately (not waiting for onMounted)
  // This ensures listeners are registered even if onMounted is delayed
  setupListeners()

  return {
    // State
    pendingRequest,
    trustedDevices,
    blacklistedDevices,
    settings,
    countdown,
    loading,

    // Actions
    fetchDevices,
    fetchSettings,
    handleResponse,
    removeDevice,
    setPolicy,
    saveSettings,
  }
})
