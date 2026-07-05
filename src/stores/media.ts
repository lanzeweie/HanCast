import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { MediaInfo, MediaInputState } from '@/types/media'
import { parseMediaFile, parseMediaUrl } from '@/api/commands'

export const useMediaStore = defineStore('media', () => {
  const state = ref<MediaInputState>('idle')
  const mediaInfo = ref<MediaInfo | null>(null)
  const urlInput = ref('')
  const error = ref<string | null>(null)

  const isReady = computed(() => state.value === 'ready' && mediaInfo.value !== null)
  const isParsing = computed(() => state.value === 'parsing')

  function reset() {
    state.value = 'idle'
    mediaInfo.value = null
    urlInput.value = ''
    error.value = null
  }

  function setDragOver() {
    if (state.value === 'idle') {
      state.value = 'dragover'
    }
  }

  function clearDragOver() {
    if (state.value === 'dragover') {
      state.value = 'idle'
    }
  }

  function setInputChange(value: string) {
    urlInput.value = value
    if (value.trim()) {
      state.value = 'input'
    } else if (state.value === 'input') {
      state.value = 'idle'
    }
  }

  async function parseFile(filePath: string) {
    state.value = 'parsing'
    error.value = null
    try {
      mediaInfo.value = await parseMediaFile(filePath)
      state.value = 'ready'
    } catch (err) {
      error.value = String(err)
      state.value = 'idle'
    }
  }

  async function parseUrl(url?: string) {
    const targetUrl = url ?? urlInput.value.trim()
    if (!targetUrl) return

    state.value = 'parsing'
    error.value = null
    try {
      mediaInfo.value = await parseMediaUrl(targetUrl)
      state.value = 'ready'
    } catch (err) {
      error.value = String(err)
      state.value = 'idle'
    }
  }

  return {
    state,
    mediaInfo,
    urlInput,
    error,
    isReady,
    isParsing,
    reset,
    setDragOver,
    clearDragOver,
    setInputChange,
    parseFile,
    parseUrl,
  }
})
