import { ref, computed, onMounted, onUnmounted } from 'vue'
import { defineStore } from 'pinia'
import type { CastState, CastSession } from '@/types/cast'
import { createSession } from '@/types/cast'
import type { UnlistenFn } from '@tauri-apps/api/event'
import {
  getCastState,
  getCastUrl,
  startCast as apiStartCast,
  stopCast as apiStopCast,
  pauseCast as apiPauseCast,
  resumeCast as apiResumeCast,
  seekCast as apiSeekCast,
  setVolume as apiSetVolume,
  setMute as apiSetMute,
} from '@/api/commands'

/** Parse "HH:MM:SS" to total seconds */
function parseTimeToSeconds(time: string): number {
  if (!time) return 0
  const parts = time.split(':').map(Number)
  if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2]
  if (parts.length === 2) return parts[0] * 60 + parts[1]
  return parts[0] || 0
}

export const useCastStore = defineStore('cast', () => {
  // ── Multi-device sessions ──
  const sessions = ref<Record<string, CastSession>>({})
  const focusedDeviceId = ref<string | null>(null)
  const loading = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  // ── Progress simulation timers ──
  // Key: deviceId, Value: timer that increments position every second
  const simTimers: Record<string, ReturnType<typeof setInterval>> = {}

  // ── Embedded controller modal state ──
  const showController = ref(false)

  // ── Computed: active session helpers ──
  const activeDeviceIds = computed(() =>
    Object.keys(sessions.value).filter(id =>
      ['connecting', 'playing', 'paused'].includes(sessions.value[id].status)
    )
  )

  const isCasting = computed(() => activeDeviceIds.value.length > 0)

  /** Get the session currently shown in the controller */
  const focusedSession = computed<CastSession | null>(() => {
    const id = focusedDeviceId.value
    return id ? (sessions.value[id] ?? null) : null
  })

  /** Backward-compat: castState looks like the old single-device state */
  const castState = computed<CastState>(() => {
    const s = focusedSession.value
    if (s) return {
      status: s.status,
      device_id: s.device_id,
      device_name: s.device_name,
      media: s.media,
      position: s.position,
      volume: s.volume,
      is_muted: s.is_muted,
      positionTime: s.positionTime,
      durationTime: s.durationTime,
    }
    return {
      status: 'idle',
      device_id: null,
      media: null,
      position: 0,
      volume: 80,
      is_muted: false,
      positionTime: '00:00:00',
      durationTime: '00:00:00',
    }
  })

  const isIdle = computed(() => castState.value.status === 'idle')
  const isPlaying = computed(() => castState.value.status === 'playing')
  const durationSeconds = computed(() => parseTimeToSeconds(castState.value.durationTime))
  const positionSeconds = computed(() => castState.value.position)

  // ── Session helpers ──
  function getSession(deviceId: string): CastSession | undefined {
    return sessions.value[deviceId]
  }

  function updateSession(deviceId: string, updates: Partial<CastSession>) {
    const existing = sessions.value[deviceId]
    if (!existing) return
    sessions.value = {
      ...sessions.value,
      [deviceId]: { ...existing, ...updates },
    }
  }

  function removeSession(deviceId: string) {
    stopSim(deviceId)
    const { [deviceId]: _, ...rest } = sessions.value
    sessions.value = rest
    if (focusedDeviceId.value === deviceId) {
      // User explicitly stopped this device → clear focus and hide controller
      // Do NOT auto-switch to another device; user can manually open another controller
      focusedDeviceId.value = null
      showController.value = false
    }
  }

  // ── Local state updates (for immediate visual feedback) ──
  function setLocalVolume(volume: number) {
    const id = focusedDeviceId.value
    if (id) updateSession(id, { volume })
  }

  // ── Controller ──
  function openController(deviceId?: string) {
    if (deviceId) focusedDeviceId.value = deviceId
    showController.value = true
  }

  function minimizeController() {
    showController.value = false
  }

  function restoreController(deviceId?: string) {
    if (deviceId) focusedDeviceId.value = deviceId
    showController.value = true
  }

  // ── Fetch state (on mount) ──
  const unlistenFns: UnlistenFn[] = []

  async function fetchState() {
    try {
      const state = await getCastState()
      // If backend returns a session, merge into existing sessions
      // But skip if a session with this device_id is already 'connecting'
      // (i.e. startCast already created it and is still awaiting apiStartCast)
      if (state.device_id && state.status !== 'idle') {
        const existing = sessions.value[state.device_id]
        if (!existing || existing.status !== 'connecting') {
          sessions.value = {
            ...sessions.value,
            [state.device_id]: {
              device_id: state.device_id,
              device_name: state.device_name ?? state.device_id,
              status: state.status,
              media: state.media,
              position: state.position,
              volume: state.volume,
              is_muted: state.is_muted,
              positionTime: state.positionTime,
              durationTime: state.durationTime,
            },
          }
        }
        if (!focusedDeviceId.value) focusedDeviceId.value = state.device_id
      }
    } catch (err) {
      console.error('Failed to get cast state:', err)
    }
  }

  // ── Polling (iterates all active sessions) ──
  function startPolling() {
    if (pollTimer) return
    pollTimer = setInterval(async () => {
      const ids = activeDeviceIds.value
      if (ids.length === 0) {
        stopPolling()
        return
      }
      const statusMap: Record<string, CastSession['status']> = {
        PLAYING: 'playing',
        PAUSED: 'paused',
        STOPPED: 'stopped',
      }
      for (const id of ids) {
        try {
          const info = await getCastUrl(id)
          const session = sessions.value[id]
          if (!session) continue
          const newStatus = statusMap[info.status] ?? session.status
          const updates: Partial<CastSession> = {}

          // Status: only upgrade (connecting→playing, paused→playing)
          // Never downgrade playing/paused→stopped from polling alone
          // (events are the source of truth for status)
          if (newStatus !== session.status && !(session.status === 'playing' || session.status === 'paused')) {
            updates.status = newStatus
          }

          // Position/duration: update from polling, but skip if values are
          // all-zero while session is playing (getCastUrl returns stale data)
          const posSec = info.position ? parseTimeToSeconds(info.position) : 0
          const durSec = info.duration ? parseTimeToSeconds(info.duration) : 0
          const pollingDataInvalid = posSec === 0 && durSec === 0 && (session.status === 'playing' || session.status === 'paused')
          if (!pollingDataInvalid) {
            if (info.position) {
              // Take the larger value — simulation may have advanced past polling
              // This ensures progress never goes backward
              const maxPos = Math.max(posSec, session.position)
              updates.position = maxPos
              updates.positionTime = formatSecondsToTime(maxPos)
            }
            if (info.duration) {
              updates.durationTime = info.duration
            }
          }

          if (Object.keys(updates).length > 0) {
            updateSession(id, updates)
          }

          // NOTE: polling never schedules removeSession — STOPPED is handled by cast_state_changed events only
        } catch {
          // Device may have gone offline
        }
      }
    }, 1000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  // ── Progress simulation (frontend-side position increment) ──
  function startSim(deviceId: string) {
    // Already simulating for this device
    if (simTimers[deviceId]) return
    simTimers[deviceId] = setInterval(() => {
      const session = sessions.value[deviceId]
      if (!session || session.status !== 'playing') {
        stopSim(deviceId)
        return
      }
      // Increment position by 1 second
      const newPosition = session.position + 1
      // Cap at duration if known
      const dur = parseTimeToSeconds(session.durationTime)
      if (dur > 0 && newPosition >= dur) {
        stopSim(deviceId)
        return
      }
      updateSession(deviceId, {
        position: newPosition,
        positionTime: formatSecondsToTime(newPosition),
      })
    }, 1000)
  }

  function stopSim(deviceId: string) {
    if (simTimers[deviceId]) {
      clearInterval(simTimers[deviceId])
      delete simTimers[deviceId]
    }
  }

  function stopAllSim() {
    for (const id of Object.keys(simTimers)) {
      clearInterval(simTimers[id])
      delete simTimers[id]
    }
  }

  /** Format total seconds back to "HH:MM:SS" */
  function formatSecondsToTime(seconds: number): string {
    const h = Math.floor(seconds / 3600)
    const m = Math.floor((seconds % 3600) / 60)
    const s = Math.floor(seconds % 60)
    const hh = String(h).padStart(2, '0')
    const mm = String(m).padStart(2, '0')
    const ss = String(s).padStart(2, '0')
    return `${hh}:${mm}:${ss}`
  }

  // ── Cast actions ──
  async function startCast(deviceId: string, mediaUri: string, mediaInfo?: { title?: string; mime_type?: string; thumbnail?: string | null }) {
    loading.value = true
    try {
      await apiStartCast(deviceId, mediaUri, mediaInfo?.mime_type)
      // Preserve existing session's volume/mute if restarting on same device
      const existing = sessions.value[deviceId]
      sessions.value = {
        ...sessions.value,
        [deviceId]: {
          ...createSession(deviceId, existing?.device_name ?? deviceId),
          status: 'playing', // Set playing immediately — don't wait for event
          volume: existing?.volume ?? 80,
          is_muted: existing?.is_muted ?? false,
          media: {
            media_type: 'url',
            uri: mediaUri,
            title: mediaInfo?.title ?? mediaUri.split('/').pop() ?? mediaUri,
            mime_type: mediaInfo?.mime_type ?? '',
            file_size: null,
            duration: null,
            thumbnail: mediaInfo?.thumbnail ?? null,
          },
        },
      }
      focusedDeviceId.value = deviceId
      startPolling()
      openController(deviceId)
      // Start progress simulation immediately — don't wait for cast_state_changed event
      // The device will start playing very soon after apiStartCast succeeds
      startSim(deviceId)
    } catch (err) {
      const session = sessions.value[deviceId]
      if (session) updateSession(deviceId, { status: 'error' })
      console.error('Failed to start cast:', err)
    } finally {
      loading.value = false
    }
  }

  async function stopCast(deviceId?: string) {
    loading.value = true
    try {
      await apiStopCast(deviceId)
      if (deviceId) {
        stopSim(deviceId)
        removeSession(deviceId)
      } else {
        // Stop all
        stopAllSim()
        sessions.value = {}
        focusedDeviceId.value = null
        showController.value = false
      }
      if (activeDeviceIds.value.length === 0) {
        stopPolling()
        showController.value = false
      }
    } catch (err) {
      console.error('Failed to stop cast:', err)
    } finally {
      loading.value = false
    }
  }

  async function pauseCast(deviceId?: string) {
    const id = deviceId ?? focusedDeviceId.value
    if (!id) return
    try {
      await apiPauseCast(id)
      stopSim(id)
      updateSession(id, { status: 'paused' })
    } catch (err) {
      console.error('Failed to pause cast:', err)
    }
  }

  async function resumeCast(deviceId?: string) {
    const id = deviceId ?? focusedDeviceId.value
    if (!id) return
    try {
      await apiResumeCast(id)
      updateSession(id, { status: 'playing' })
      startSim(id)
    } catch (err) {
      console.error('Failed to resume cast:', err)
    }
  }

  async function seek(position: string, deviceId?: string) {
    const id = deviceId ?? focusedDeviceId.value
    if (!id) return
    try {
      await apiSeekCast(position, id)
      // Update position immediately for responsive UI
      const posSec = parseTimeToSeconds(position)
      updateSession(id, { position: posSec, positionTime: position })
      // Restart simulation from new position
      stopSim(id)
      const session = sessions.value[id]
      if (session?.status === 'playing') {
        startSim(id)
      }
    } catch (err) {
      console.error('Failed to seek:', err)
    }
  }

  async function setVolume(volume: number, deviceId?: string): Promise<number> {
    const id = deviceId ?? focusedDeviceId.value
    if (!id) return volume
    try {
      const result = await apiSetVolume(volume, id)
      updateSession(id, { volume: result })
      return result
    } catch (err) {
      console.error('Failed to set volume:', err)
      return sessions.value[id]?.volume ?? volume
    }
  }

  async function setMute(muted: boolean, deviceId?: string): Promise<void> {
    const id = deviceId ?? focusedDeviceId.value
    if (!id) return
    try {
      await apiSetMute(muted, id)
      updateSession(id, { is_muted: muted })
    } catch (err) {
      console.error('Failed to set mute:', err)
    }
  }

  // ── Event listeners ──
  async function setupListeners() {
    try {
      const { listen } = await import('@tauri-apps/api/event')

      unlistenFns.push(
        await listen<{ device_id?: string; status: string; position?: string; duration?: string; volume?: number; is_muted?: boolean }>('cast_state_changed', (event) => {
          const { device_id, status, position, duration } = event.payload
          const mappedStatus: Record<string, CastSession['status']> = {
            PLAYING: 'playing',
            PAUSED: 'paused',
            STOPPED: 'stopped',
            NO_MEDIA_PRESENT: 'idle',
          }
          const newStatus = mappedStatus[status] ?? status as CastSession['status']

          // Determine which device this event is for
          // Fallback: single session in store → use it; otherwise use focused device
          const sessionIds = Object.keys(sessions.value)
          const targetId = device_id
            ?? (sessionIds.length === 1 ? sessionIds[0] : focusedDeviceId.value)
          if (!targetId) return

          const session = sessions.value[targetId]
          if (!session) return

          // Read current status BEFORE updating (guard depends on it)
          const prevStatus = sessions.value[targetId]?.status

          // Build updates
          const updates: Partial<CastSession> = { status: newStatus }
          if (position) {
            updates.position = parseTimeToSeconds(position)
            updates.positionTime = position
          }
          if (duration) {
            updates.durationTime = duration
          }
          if (event.payload.volume !== undefined) {
            updates.volume = event.payload.volume
          }
          if (event.payload.is_muted !== undefined) {
            updates.is_muted = event.payload.is_muted
          }

          updateSession(targetId, updates)

          // Start/stop progress simulation based on status
          if (newStatus === 'playing') {
            startSim(targetId)
          } else if (newStatus === 'paused' || newStatus === 'stopped' || newStatus === 'idle') {
            stopSim(targetId)
          }

          // Video finished or device stopped
          // Never remove sessions that are connecting, playing, or paused
          // (DLNA may send transient NO_MEDIA_PRESENT / STOPPED during playback)
          if (newStatus === 'stopped' || newStatus === 'idle') {
            if (prevStatus === 'connecting' || prevStatus === 'playing' || prevStatus === 'paused') {
              return
            }
            const removeTargetId = targetId
            setTimeout(() => {
              const s = sessions.value[removeTargetId]
              if (s && (s.status === 'stopped' || s.status === 'idle')) {
                removeSession(removeTargetId)
              }
            }, 500)
            if (focusedDeviceId.value === targetId) {
              showController.value = false
            }
            if (activeDeviceIds.value.length <= 1) {
              stopPolling()
            }
          }
        })
      )

      unlistenFns.push(
        await listen<{ device_id?: string; message: string }>('cast_error', (event) => {
          const targetId = event.payload.device_id ?? focusedDeviceId.value
          if (targetId && sessions.value[targetId]) {
            stopSim(targetId)
            updateSession(targetId, { status: 'error' })
          }
          console.error('Cast error:', event.payload.message)
        })
      )
    } catch {
      // Running outside Tauri, skip listeners
    }
  }

  onMounted(() => {
    fetchState().then(() => {
      if (activeDeviceIds.value.length > 0) {
        startPolling()
      }
    })
    setupListeners()
  })

  onUnmounted(() => {
    stopPolling()
    stopAllSim()
    unlistenFns.forEach((fn) => fn())
  })

  return {
    // Multi-device state
    sessions,
    focusedDeviceId,
    focusedSession,
    activeDeviceIds,
    loading,
    showController,

    // Backward-compat (single-device view via focusedSession)
    castState,
    isIdle,
    isPlaying,
    isCasting,
    durationSeconds,
    positionSeconds,

    // Session helpers
    getSession,
    updateSession,

    // Controller
    openController,
    minimizeController,
    restoreController,

    // Local updates
    setLocalVolume,

    // Actions
    fetchState,
    startCast,
    stopCast,
    pauseCast,
    resumeCast,
    seek,
    setVolume,
    setMute,
  }
})
