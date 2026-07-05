<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useMediaStore } from '@/stores/media'
import { useDeviceStore } from '@/stores/device'
import { useCastStore } from '@/stores/cast'

const { t } = useI18n()
const mediaStore = useMediaStore()
const deviceStore = useDeviceStore()
const castStore = useCastStore()

const dragCounter = ref(0)

const stateLabel = computed(() => {
  switch (mediaStore.state) {
    case 'dragover': return t('media.dragHint')
    case 'input': return ''
    case 'parsing': return t('media.parsing')
    case 'ready': return t('media.ready')
    default: return t('media.dragHint')
  }
})

function onDragEnter(e: DragEvent) {
  e.preventDefault()
  dragCounter.value++
  mediaStore.setDragOver()
}

function onDragLeave(e: DragEvent) {
  e.preventDefault()
  dragCounter.value--
  if (dragCounter.value <= 0) {
    dragCounter.value = 0
    mediaStore.clearDragOver()
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  dragCounter.value = 0
  mediaStore.clearDragOver()

  const files = e.dataTransfer?.files
  if (files && files.length > 0) {
    const file = files[0]
    // @ts-expect-error Tauri path
    const path = file.path || file.name
    mediaStore.parseFile(path)
  }
}

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

// Handle file input for non-Tauri environments
const fileInput = ref<HTMLInputElement>()
function openFilePicker() {
  fileInput.value?.click()
}
function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) {
    // @ts-expect-error Tauri path
    const path = file.path || file.name
    mediaStore.parseFile(path)
  }
}
</script>

<template>
  <div
    class="media-input"
    :class="{
      'media-input--dragover': mediaStore.state === 'dragover',
      'media-input--parsing': mediaStore.state === 'parsing',
      'media-input--ready': mediaStore.state === 'ready',
    }"
    @dragenter="onDragEnter"
    @dragleave="onDragLeave"
    @dragover="onDragOver"
    @drop="onDrop"
  >
    <input
      ref="fileInput"
      type="file"
      accept="video/*,audio/*,image/*"
      style="display: none"
      @change="onFileSelected"
    />

    <!-- Drag / Default State -->
    <div class="media-input__dropzone" v-if="mediaStore.state !== 'ready'" @click="openFilePicker">
      <div class="media-input__icon">
        <svg viewBox="0 0 64 64" width="64" height="64">
          <!-- Folder body -->
          <rect x="8" y="18" width="48" height="36" rx="4" fill="#60A5FA" />
          <path d="M8 22C8 19.79 9.79 18 12 18H26L30 14H52C54.21 14 56 15.79 56 18V22H8Z" fill="#3B82F6" />
          <!-- Play icon -->
          <polygon points="26,30 26,44 38,37" fill="white" opacity="0.9" />
          <!-- Music note -->
          <circle cx="44" cy="38" r="3" fill="white" opacity="0.7" />
          <path d="M44 35V28" stroke="white" stroke-width="2" opacity="0.7" />
          <!-- Image icon -->
          <rect x="14" y="32" width="10" height="8" rx="1" fill="white" opacity="0.5" />
          <circle cx="17" cy="35" r="1.5" fill="#60A5FA" opacity="0.7" />
        </svg>
      </div>

      <p class="media-input__hint">{{ t('media.dragHint') }}</p>
      <p class="media-input__subhint">{{ t('media.pasteHint') }}</p>
    </div>

    <!-- Ready State -->
    <div class="media-input__ready" v-else>
      <div class="media-input__ready-info">
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="var(--primary)" stroke-width="2">
          <path d="M14.5 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V7.5L14.5 2z" />
          <polyline points="14,2 14,8 20,8" />
        </svg>
        <span class="media-input__ready-title">{{ mediaStore.mediaInfo?.title }}</span>
      </div>
    </div>

    <!-- URL Input Bar -->
    <div class="media-input__urlbar">
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

    <!-- Cast Button (when ready) -->
    <button
      v-if="mediaStore.isReady"
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
}

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

.media-input__ready {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
}

.media-input__ready-info {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
}

.media-input__ready-title {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* URL bar */
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

/* Cast button */
.media-input__cast-btn {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  padding: 8px 20px;
  font-size: 14px;
  font-weight: 500;
  color: white;
  background: var(--primary);
  border-radius: var(--r-full);
  transition: background var(--transition-fast);
}

.media-input__cast-btn:hover:not(:disabled) {
  background: var(--primary-hover);
}

.media-input__cast-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
