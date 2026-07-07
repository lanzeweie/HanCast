import { ref, computed, onMounted, onUnmounted } from 'vue'
import { defineStore } from 'pinia'
import type { CastState } from '@/types/cast'
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
  const castState = ref<CastState>({
    status: 'idle',
    device_id: null,
    media: null,
    position: 0,
    volume: 80,
    is_muted: false,
    positionTime: '00:00:00',
    durationTime: '00:00:00',
  })
  const loading = ref(false)
  let pollTimer: ReturnType<typeof setInterval> | null = null

  // ── Embedded controller modal state ──
  const showController = ref(false)

  function openController() {
    showController.value = true
  }

  function minimizeController() {
    showController.value = false
  }

  function restoreController() {
    showController.value = true
  }

  const isIdle = computed(() => castState.value.status === 'idle')
  const isPlaying = computed(() => castState.value.status === 'playing')
  const isCasting = computed(() =>
    ['connecting', 'playing', 'paused'].includes(castState.value.status)
  )

  const durationSeconds = computed(() => parseTimeToSeconds(castState.value.durationTime))
  const positionSeconds = computed(() => castState.value.position)

  const unlistenFns: UnlistenFn[] = []

  async function fetchState() {
    try {
      castState.value = await getCastState()
    } catch (err) {
      console.error('Failed to get cast state:', err)
    }
  }

  function startPolling() {
    if (pollTimer) return
    console.log('[Cast] Polling started')
    pollTimer = setInterval(async () => {
      try {
        const info = await getCastUrl()
        console.log('[Cast] Poll:', info)
        const statusMap: Record<string, CastState['status']> = {
          PLAYING: 'playing',
          PAUSED: 'paused',
          STOPPED: 'stopped',
        }
        castState.value = {
          ...castState.value,
          status: statusMap[info.status] ?? castState.value.status,
          position: parseTimeToSeconds(info.position),
          positionTime: info.position,
          durationTime: info.duration,
        }
        if (info.status === 'STOPPED') {
          stopPolling()
        }
      } catch (err) {
        console.error('Failed to poll cast url:', err)
      }
    }, 1000)
  }

  function stopPolling() {
    if (pollTimer) {
      clearInterval(pollTimer)
      pollTimer = null
    }
  }

  async function startCast(deviceId: string, mediaUri: string, mediaInfo?: { title?: string; mime_type?: string; thumbnail?: string | null }) {
    loading.value = true
    try {
      await apiStartCast(deviceId, mediaUri)
      castState.value = {
        ...castState.value,
        status: 'connecting',
        device_id: deviceId,
        media: {
          media_type: 'url',
          uri: mediaUri,
          title: mediaInfo?.title ?? mediaUri.split('/').pop() ?? mediaUri,
          mime_type: mediaInfo?.mime_type ?? '',
          file_size: null,
          duration: null,
          thumbnail: mediaInfo?.thumbnail ?? null,
        },
      }
      startPolling()
      // Show embedded controller
      openController()
    } catch (err) {
      castState.value = { ...castState.value, status: 'error' }
      console.error('Failed to start cast:', err)
    } finally {
      loading.value = false
    }
  }

  async function stopCast() {
    loading.value = true
    stopPolling()
    try {
      await apiStopCast()
      castState.value = {
        status: 'idle',
        device_id: null,
        media: null,
        position: 0,
        volume: castState.value.volume,
        is_muted: castState.value.is_muted,
        positionTime: '00:00:00',
        durationTime: '00:00:00',
      }
      // Hide controller
      showController.value = false
    } catch (err) {
      console.error('Failed to stop cast:', err)
    } finally {
      loading.value = false
    }
  }

  async function pauseCast() {
    try {
      await apiPauseCast()
      castState.value = { ...castState.value, status: 'paused' }
    } catch (err) {
      console.error('Failed to pause cast:', err)
    }
  }

  async function resumeCast() {
    try {
      await apiResumeCast()
      castState.value = { ...castState.value, status: 'playing' }
    } catch (err) {
      console.error('Failed to resume cast:', err)
    }
  }

  async function seek(position: string) {
    try {
      await apiSeekCast(position)
    } catch (err) {
      console.error('Failed to seek:', err)
    }
  }

  async function setVolume(volume: number): Promise<number> {
    try {
      const result = await apiSetVolume(volume)
      castState.value = { ...castState.value, volume: result }
      return result
    } catch (err) {
      console.error('Failed to set volume:', err)
      return castState.value.volume
    }
  }

  // Set up event listeners
  async function setupListeners() {
    try {
      const { listen } = await import('@tauri-apps/api/event')

      unlistenFns.push(
        await listen<{ status: string; volume?: number; is_muted?: boolean }>('cast_state_changed', (event) => {
          const { status } = event.payload
          const mappedStatus: Record<string, CastState['status']> = {
            PLAYING: 'playing',
            PAUSED: 'paused',
            STOPPED: 'stopped',
            NO_MEDIA_PRESENT: 'idle',
          }
          const newStatus = mappedStatus[status] ?? status as CastState['status']

          // Update volume/mute if provided
          if (event.payload.volume !== undefined) {
            castState.value.volume = event.payload.volume
          }
          if (event.payload.is_muted !== undefined) {
            castState.value.is_muted = event.payload.is_muted
          }

          castState.value = { ...castState.value, status: newStatus }

          // Video finished or device stopped
          if (newStatus === 'stopped' || newStatus === 'idle') {
            stopPolling()
            showController.value = false
          }
        })
      )

      unlistenFns.push(
        await listen<{ message: string }>('cast_error', (event) => {
          console.error('Cast error:', event.payload.message)
          castState.value = { ...castState.value, status: 'error' }
        })
      )
    } catch {
      // Running outside Tauri, skip listeners
    }
  }

  onMounted(() => {
    fetchState().then(() => {
      if (['playing', 'paused', 'connecting'].includes(castState.value.status)) {
        startPolling()
      }
    })
    setupListeners()
  })

  onUnmounted(() => {
    stopPolling()
    unlistenFns.forEach((fn) => fn())
  })

  return {
    castState,
    loading,
    isIdle,
    isPlaying,
    isCasting,
    showController,
    durationSeconds,
    positionSeconds,
    fetchState,
    startCast,
    stopCast,
    pauseCast,
    resumeCast,
    seek,
    setVolume,
    openController,
    minimizeController,
    restoreController,
  }
})
