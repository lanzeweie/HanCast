import { ref, computed } from 'vue'
import { defineStore } from 'pinia'
import type { MediaInfo, MediaInputState } from '@/types/media'
import { parseMediaFile, resolveBilibili } from '@/api/commands'

/** Check if URL is a Bilibili link */
function isBilibiliUrl(url: string): boolean {
  return /bilibili\.com|b23\.tv|bilibili\.tv/i.test(url)
}

/** Infer MIME type from filename extension */
function inferMime(name: string): string {
  const ext = name.split('.').pop()?.toLowerCase() ?? ''
  const map: Record<string, string> = {
    mp4: 'video/mp4', mkv: 'video/x-matroska', avi: 'video/x-msvideo',
    mov: 'video/quicktime', webm: 'video/webm', flv: 'video/x-flv',
    mp3: 'audio/mpeg', flac: 'audio/flac', wav: 'audio/wav',
    aac: 'audio/aac', ogg: 'audio/ogg', m4a: 'audio/mp4',
    jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
    gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp',
  }
  return map[ext] ?? 'application/octet-stream'
}

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
    localFile.value = null
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

  /** Store the browser File object so the component can create preview URLs */
  const localFile = ref<File | null>(null)

  async function parseFile(filePathOrFile: string | File) {
    state.value = 'parsing'
    error.value = null
    try {
      if (typeof filePathOrFile === 'string') {
        // Tauri mode: send path to backend
        mediaInfo.value = await parseMediaFile(filePathOrFile)
        localFile.value = null
      } else {
        // Browser mode: extract info from File object directly
        const file = filePathOrFile
        localFile.value = file
        mediaInfo.value = {
          media_type: 'file',
          uri: file.name,
          title: file.name,
          mime_type: file.type || inferMime(file.name),
          file_size: file.size,
          duration: null,
          thumbnail: null,
        }
      }
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
      // Bilibili: resolve via backend
      if (isBilibiliUrl(targetUrl)) {
        const result = await resolveBilibili(targetUrl)
        mediaInfo.value = result
        state.value = 'ready'
        return
      }

      const parsed = new URL(targetUrl)
      const pathParts = parsed.pathname.split('/')
      const title = decodeURIComponent(pathParts[pathParts.length - 1]) || targetUrl

      // Infer MIME from extension (no network request needed)
      const ext = title.split('.').pop()?.toLowerCase() ?? ''
      const mimeMap: Record<string, string> = {
        mp4: 'video/mp4', mkv: 'video/x-matroska', avi: 'video/x-msvideo',
        mov: 'video/quicktime', webm: 'video/webm', flv: 'video/x-flv',
        mp3: 'audio/mpeg', flac: 'audio/flac', wav: 'audio/wav',
        aac: 'audio/aac', ogg: 'audio/ogg', m4a: 'audio/mp4',
        jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
        gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp',
      }
      const mime = mimeMap[ext] ?? ''

      mediaInfo.value = {
        media_type: 'url',
        uri: targetUrl,
        title,
        mime_type: mime,
        file_size: null,
        duration: null,
        thumbnail: null,
      }
      state.value = 'ready'
    } catch (err) {
      error.value = String(err)
      state.value = 'idle'
    }
  }

  return {
    state,
    mediaInfo,
    localFile,
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
