import { ref, computed, onMounted, onUnmounted } from 'vue'
import { defineStore } from 'pinia'
import type { CastState } from '@/types/cast'
import type { UnlistenFn } from '@tauri-apps/api/event'
import {
  getCastState,
  startCast as apiStartCast,
  stopCast as apiStopCast,
  pauseCast as apiPauseCast,
  resumeCast as apiResumeCast,
  seekCast as apiSeekCast,
} from '@/api/commands'

export const useCastStore = defineStore('cast', () => {
  const castState = ref<CastState>({
    status: 'idle',
    device_id: null,
    media: null,
    position: 0,
    volume: 80,
    is_muted: false,
  })
  const loading = ref(false)

  const isIdle = computed(() => castState.value.status === 'idle')
  const isPlaying = computed(() => castState.value.status === 'playing')
  const isCasting = computed(() =>
    ['connecting', 'playing', 'paused'].includes(castState.value.status)
  )

  const unlistenFns: UnlistenFn[] = []

  async function fetchState() {
    try {
      castState.value = await getCastState()
    } catch (err) {
      console.error('Failed to get cast state:', err)
    }
  }

  async function startCast(deviceId: string, mediaUri: string) {
    loading.value = true
    try {
      await apiStartCast(deviceId, mediaUri)
      castState.value = {
        ...castState.value,
        status: 'connecting',
        device_id: deviceId,
      }
    } catch (err) {
      castState.value = { ...castState.value, status: 'error' }
      console.error('Failed to start cast:', err)
    } finally {
      loading.value = false
    }
  }

  async function stopCast() {
    loading.value = true
    try {
      await apiStopCast()
      castState.value = {
        status: 'idle',
        device_id: null,
        media: null,
        position: 0,
        volume: castState.value.volume,
        is_muted: castState.value.is_muted,
      }
    } catch (err) {
      console.error('Failed to stop cast:', err)
    } finally {
      loading.value = false
    }
  }

  async function pauseCast() {
    try {
      await apiPauseCast()
    } catch (err) {
      console.error('Failed to pause cast:', err)
    }
  }

  async function resumeCast() {
    try {
      await apiResumeCast()
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

  // Set up event listeners
  async function setupListeners() {
    try {
      const { listen } = await import('@tauri-apps/api/event')

      // Cast state changed
      unlistenFns.push(
        await listen<CastState>('cast_state_changed', (event) => {
          castState.value = event.payload
        })
      )

      // Cast error
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
    fetchState()
    setupListeners()
  })

  onUnmounted(() => {
    unlistenFns.forEach((fn) => fn())
  })

  return {
    castState,
    loading,
    isIdle,
    isPlaying,
    isCasting,
    fetchState,
    startCast,
    stopCast,
    pauseCast,
    resumeCast,
    seek,
  }
})
