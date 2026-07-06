<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMediaStore } from '@/stores/media'
import { useDeviceStore } from '@/stores/device'
import { useCastStore } from '@/stores/cast'

const { t } = useI18n()
const mediaStore = useMediaStore()
const deviceStore = useDeviceStore()
const castStore = useCastStore()

const isDragOver = ref(false)
const pickerError = ref<string | null>(null)

// ── Media type detection ──

type MediaCategory = 'video' | 'image' | 'audio' | 'link'

function getMediaCategory(): MediaCategory {
  const mime = mediaStore.mediaInfo?.mime_type ?? ''
  if (mime.startsWith('video/')) return 'video'
  if (mime.startsWith('image/')) return 'image'
  if (mime.startsWith('audio/')) return 'audio'
  return 'link'
}

const mediaCategory = computed<MediaCategory>(() => getMediaCategory())

const categoryIcon = computed(() => {
  switch (mediaCategory.value) {
    case 'video': return '🎬'
    case 'image': return '🖼️'
    case 'audio': return '🎵'
    case 'link': return '🔗'
  }
})

const categoryLabel = computed(() => {
  switch (mediaCategory.value) {
    case 'video': return t('media.video')
    case 'image': return t('media.image')
    case 'audio': return t('media.audio')
    case 'link': return t('media.link')
  }
})

// ── Formatters ──

function formatFileSize(bytes: number | null): string | null {
  if (!bytes) return null
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  if (bytes < 1024 * 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(1) + ' MB'
  return (bytes / (1024 * 1024 * 1024)).toFixed(2) + ' GB'
}

function formatDuration(seconds: number | null): string | null {
  if (!seconds || seconds <= 0) return null
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  if (h > 0) return `${h}:${mm}:${ss}`
  return `${mm}:${ss}`
}

/** Build the subtitle line: "video/mp4 · 48.8 MB · 01:23:45" */
const mediaSubtitle = computed(() => {
  const info = mediaStore.mediaInfo
  if (!info) return ''
  const parts: string[] = []
  // MIME type (short form)
  if (info.mime_type) {
    parts.push(info.mime_type)
  }
  const size = formatFileSize(info.file_size)
  if (size) parts.push(size)
  const dur = formatDuration(info.duration)
  if (dur) parts.push(dur)
  return parts.join(' · ') || categoryLabel.value
})

// ── Tauri Native Drag & Drop ──
// Tauri 2.0 intercepts OS-level file drops; HTML5 drag events never fire.
// We use the raw tauri://drag-drop event for maximum compatibility.

let unlistenDrag: (() => void) | null = null
let inTauri = false

// ── HTML5 fallback for browser dev mode ──
const dragCounter = ref(0)

function onHtmlDragEnter(e: DragEvent) {
  if (inTauri) return
  e.preventDefault()
  dragCounter.value++
  mediaStore.setDragOver()
}

function onHtmlDragLeave(e: DragEvent) {
  if (inTauri) return
  e.preventDefault()
  dragCounter.value--
  if (dragCounter.value <= 0) {
    dragCounter.value = 0
    mediaStore.clearDragOver()
  }
}

function onHtmlDragOver(e: DragEvent) {
  if (inTauri) return
  e.preventDefault()
}

function onHtmlDrop(e: DragEvent) {
  if (inTauri) return
  e.preventDefault()
  dragCounter.value = 0
  mediaStore.clearDragOver()
  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    const file = files[0]
    // @ts-expect-error Tauri 1.x path injection
    const path = file.path || file.name
    mediaStore.parseFile(path)
  }
}

onMounted(async () => {
  try {
    // Tauri 2.0: drag-drop events are on the Webview, not the Window
    const { getCurrentWebview } = await import('@tauri-apps/api/webview')
    const webview = getCurrentWebview()
    inTauri = true
    console.log('[MediaInput] Tauri detected, registering drag-drop on webview...')

    unlistenDrag = await webview.onDragDropEvent((event) => {
      console.log('[MediaInput] drag-drop:', event.payload.type, JSON.stringify(event.payload))
      if (event.payload.type === 'enter' || event.payload.type === 'over') {
        isDragOver.value = true
        mediaStore.setDragOver()
      } else if (event.payload.type === 'drop') {
        isDragOver.value = false
        mediaStore.clearDragOver()
        const paths = event.payload.paths
        console.log('[MediaInput] dropped paths:', paths)
        if (paths && paths.length > 0) {
          console.log('[MediaInput] parsing file:', paths[0])
          mediaStore.parseFile(paths[0])
        }
      } else {
        isDragOver.value = false
        mediaStore.clearDragOver()
      }
    })
    console.log('[MediaInput] drag-drop listener registered on webview')
  } catch (err) {
    console.warn('[MediaInput] Not in Tauri, using HTML5 drag-drop fallback:', err)
  }
})

onUnmounted(() => {
  unlistenDrag?.()
})

function onPasteFromClipboard() {
  navigator.clipboard.readText().then((text) => {
    if (text.trim()) {
      mediaStore.setInputChange(text.trim())
      mediaStore.parseUrl(text.trim())
    }
  }).catch(() => {
    // Clipboard API not available
  })
}

async function onParse() {
  await mediaStore.parseUrl()
}

async function onCast() {
  const device = deviceStore.selectedDevice ?? deviceStore.devices.find(d => d.status === 'online')
  if (device && mediaStore.mediaInfo) {
    await castStore.startCast(device.id, mediaStore.mediaInfo.uri)
  }
}

function onClear() {
  mediaStore.reset()
}

// File picker: try Tauri dialog first, fall back to HTML file input
async function openFilePicker() {
  pickerError.value = null
  try {
    const { open } = await import('@tauri-apps/plugin-dialog')
    console.log('[MediaInput] Opening Tauri dialog...')
    const selected = await open({
      multiple: false,
      filters: [{
        name: 'Media',
        extensions: ['mp4', 'mkv', 'avi', 'mov', 'webm', 'flv', 'mp3', 'flac', 'wav', 'aac', 'ogg', 'm4a', 'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp']
      }]
    })
    console.log('[MediaInput] Dialog returned:', typeof selected, JSON.stringify(selected))
    if (selected && typeof selected === 'string') {
      console.log('[MediaInput] Parsing file:', selected)
      await mediaStore.parseFile(selected)
      console.log('[MediaInput] Parse done, state:', mediaStore.state, 'error:', mediaStore.error)
    } else if (selected === null) {
      console.log('[MediaInput] User cancelled dialog')
    }
  } catch (err: any) {
    console.error('[MediaInput] Tauri dialog failed:', err)
    pickerError.value = String(err?.message ?? err)
    // Browser fallback
    fileInput.value?.click()
  }
}

const fileInput = ref<HTMLInputElement>()
function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    // Browser mode: only have filename, not full path
    mediaStore.parseFile(file.name)
  }
}
</script>

<template>
  <div
    class="media-input"
    :class="{
      'media-input--dragover': isDragOver || mediaStore.state === 'dragover',
      'media-input--parsing': mediaStore.state === 'parsing',
      'media-input--ready': mediaStore.state === 'ready',
    }"
    @dragenter="onHtmlDragEnter"
    @dragleave="onHtmlDragLeave"
    @dragover="onHtmlDragOver"
    @drop="onHtmlDrop"
  >
    <input
      ref="fileInput"
      type="file"
      accept="video/*,audio/*,image/*"
      style="display: none"
      @change="onFileSelected"
    />

    <!-- ═══ Drag / Default State ═══ -->
    <div
      v-if="mediaStore.state !== 'ready'"
      class="media-input__dropzone"
      @click="openFilePicker"
    >
      <div class="media-input__icon">
        <svg viewBox="0 0 64 64" width="64" height="64">
          <rect x="8" y="18" width="48" height="36" rx="4" fill="#60A5FA" />
          <path d="M8 22C8 19.79 9.79 18 12 18H26L30 14H52C54.21 14 56 15.79 56 18V22H8Z" fill="#3B82F6" />
          <polygon points="26,30 26,44 38,37" fill="white" opacity="0.9" />
          <circle cx="44" cy="38" r="3" fill="white" opacity="0.7" />
          <path d="M44 35V28" stroke="white" stroke-width="2" opacity="0.7" />
          <rect x="14" y="32" width="10" height="8" rx="1" fill="white" opacity="0.5" />
          <circle cx="17" cy="35" r="1.5" fill="#60A5FA" opacity="0.7" />
        </svg>
      </div>

      <!-- Parsing spinner -->
      <div v-if="mediaStore.state === 'parsing'" class="media-input__parsing">
        <span class="media-input__spinner" />
        <span>{{ t('media.parsing') }}</span>
      </div>
      <template v-else>
        <p class="media-input__hint">{{ t('media.dragHint') }}</p>
        <p class="media-input__subhint">{{ t('media.pasteHint') }}</p>
        <p v-if="pickerError" class="media-input__error">⚠ {{ pickerError }}</p>
        <p v-if="mediaStore.error" class="media-input__error">⚠ {{ mediaStore.error }}</p>
      </template>
    </div>

    <!-- ═══ Ready State — Media Preview Card ═══ -->
    <div v-else class="media-input__preview">
      <button class="media-input__clear" @click="onClear" :title="t('media.clear')">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18" />
          <line x1="6" y1="6" x2="18" y2="18" />
        </svg>
      </button>

      <div class="media-input__preview-body">
        <span class="media-input__preview-icon">{{ categoryIcon }}</span>
        <div class="media-input__preview-text">
          <span class="media-input__preview-title">{{ mediaStore.mediaInfo?.title }}</span>
          <span class="media-input__preview-sub">{{ mediaSubtitle }}</span>
        </div>
      </div>

      <button
        class="media-input__cast-btn"
        @click="onCast"
        :disabled="castStore.loading"
      >
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M2 16.1A5 5 0 015.9 20M2 12.05A9 9 0 019.95 20M2 8V6a2 2 0 012-2h16a2 2 0 012 2v12a2 2 0 01-2 2h-6" />
          <circle cx="2" cy="20" r="1" fill="currentColor" />
        </svg>
        {{ t('devices.cast') }}
      </button>
    </div>

    <!-- ═══ URL Input Bar (hidden when ready) ═══ -->
    <div v-if="mediaStore.state !== 'ready'" class="media-input__urlbar">
      <svg class="media-input__urlicon" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M10 13a5 5 0 007.54.54l3-3a5 5 0 00-7.07-7.07l-1.72 1.71" />
        <path d="M14 11a5 5 0 00-7.54-.54l-3 3a5 5 0 007.07 7.07l1.71-1.71" />
      </svg>
      <input
        class="media-input__urlinput"
        type="text"
        :placeholder="t('media.linkPlaceholder')"
        :value="mediaStore.urlInput"
        @input="mediaStore.setInputChange(($event.target as HTMLInputElement).value)"
        @keydown.enter="onParse"
      />
      <button class="media-input__paste" @click="onPasteFromClipboard">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="9" y="9" width="13" height="13" rx="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
        {{ t('media.paste') }}
      </button>
      <button
        class="media-input__parse"
        @click="onParse"
        :disabled="!mediaStore.urlInput.trim() || mediaStore.isParsing"
      >
        {{ t('media.parse') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.media-input {
  border: 2px dashed var(--border-dashed);
  border-radius: var(--r-xl);
  padding: var(--sp-xl);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-lg);
  transition: border-color var(--transition-normal), background var(--transition-normal);
  background: var(--bg-card);
  margin: 0 var(--sp-lg);
}

.media-input--dragover {
  border-color: var(--primary);
  background: var(--primary-light);
}

.media-input--ready {
  border-style: solid;
  border-color: var(--status-online);
  padding: var(--sp-lg);
  gap: var(--sp-md);
}

/* ── Dropzone ── */
.media-input__dropzone {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--sp-sm);
  cursor: pointer;
}

.media-input__icon {
  margin-bottom: var(--sp-sm);
}

.media-input__hint {
  font-size: 15px;
  font-weight: 500;
  color: var(--text-primary);
}

.media-input__subhint {
  font-size: 13px;
  color: var(--text-tertiary);
}

.media-input__error {
  font-size: 12px;
  color: #EF4444;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Parsing spinner ── */
.media-input__parsing {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  font-size: 14px;
  color: var(--text-secondary);
}

.media-input__spinner {
  width: 16px;
  height: 16px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* ── Preview Card ── */
.media-input__preview {
  display: flex;
  flex-direction: column;
  gap: var(--sp-md);
  width: 100%;
  position: relative;
}

.media-input__clear {
  position: absolute;
  top: 0;
  right: 0;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-full);
  color: var(--text-tertiary);
  transition: all var(--transition-fast);
}

.media-input__clear:hover {
  background: var(--bg-input);
  color: var(--text-primary);
}

.media-input__preview-body {
  display: flex;
  align-items: center;
  gap: var(--sp-md);
  min-width: 0;
}

.media-input__preview-icon {
  font-size: 32px;
  line-height: 1;
  flex-shrink: 0;
}

.media-input__preview-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.media-input__preview-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.media-input__preview-sub {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Cast button ── */
.media-input__cast-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-sm);
  width: 100%;
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  color: white;
  background: var(--primary);
  border-radius: var(--r-lg);
  transition: background var(--transition-fast);
}

.media-input__cast-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.media-input__cast-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* ── URL bar ── */
.media-input__urlbar {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  width: 100%;
  background: var(--bg-input);
  border-radius: var(--r-full);
  padding: var(--sp-xs) var(--sp-sm);
  border: 1px solid var(--border);
}

.media-input__urlicon {
  color: var(--text-tertiary);
  flex-shrink: 0;
  margin-left: var(--sp-xs);
}

.media-input__urlinput {
  flex: 1;
  min-width: 0;
  padding: var(--sp-xs) 0;
  font-size: 13px;
  color: var(--text-primary);
}

.media-input__urlinput::placeholder {
  color: var(--text-tertiary);
}

.media-input__paste {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: var(--sp-xs) var(--sp-sm);
  font-size: 12px;
  color: var(--text-secondary);
  border-radius: var(--r-sm);
  white-space: nowrap;
  flex-shrink: 0;
}

.media-input__paste:hover {
  background: var(--border);
  color: var(--text-primary);
}

.media-input__parse {
  padding: 6px 14px;
  font-size: 13px;
  font-weight: 500;
  color: white;
  background: var(--primary);
  border-radius: var(--r-full);
  white-space: nowrap;
  flex-shrink: 0;
  transition: background var(--transition-fast);
}

.media-input__parse:hover:not(:disabled) {
  background: var(--primary-hover);
}

.media-input__parse:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
