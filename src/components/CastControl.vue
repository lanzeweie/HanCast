<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCastStore } from '@/stores/cast'

const { t } = useI18n()
const castStore = useCastStore()

/** Whether the current media is an image (no playback controls needed) */
const isImage = computed(() => {
  const mime = castStore.castState.media?.mime_type ?? ''
  return mime.startsWith('image/')
})

/** Whether the current media is a video or audio (full playback controls) */
const isPlayable = computed(() => {
  const mime = castStore.castState.media?.mime_type ?? ''
  return mime.startsWith('video/') || mime.startsWith('audio/')
})

/** Whether the user is currently dragging the seek slider */
const isSeeking = ref(false)
/** Local slider value (0–100) while seeking */
const seekValue = ref(0)

/** Format seconds to HH:MM:SS or MM:SS */
function formatTime(seconds: number): string {
  if (seconds <= 0) return '00:00'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  const mm = String(m).padStart(2, '0')
  const ss = String(s).padStart(2, '0')
  if (h > 0) return `${h}:${mm}:${ss}`
  return `${mm}:${ss}`
}

const progress = computed(() => {
  const dur = castStore.durationSeconds
  if (dur <= 0) return 0
  return Math.min(100, (castStore.positionSeconds / dur) * 100)
})

const displayProgress = computed(() => {
  return isSeeking.value ? seekValue.value : progress.value
})

const displayPosition = computed(() => {
  if (isSeeking.value) {
    return formatTime((seekValue.value / 100) * castStore.durationSeconds)
  }
  return formatTime(castStore.positionSeconds)
})

const displayDuration = computed(() => formatTime(castStore.durationSeconds))

const canSeek = computed(() => castStore.durationSeconds > 0)

function onSliderInput(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  seekValue.value = val
}

function onSliderMouseDown() {
  isSeeking.value = true
  seekValue.value = progress.value
}

function onSliderMouseUp(e: Event) {
  const val = Number((e.target as HTMLInputElement).value)
  isSeeking.value = false
  if (castStore.durationSeconds > 0) {
    const targetSeconds = (val / 100) * castStore.durationSeconds
    const h = Math.floor(targetSeconds / 3600)
    const m = Math.floor((targetSeconds % 3600) / 60)
    const s = Math.floor(targetSeconds % 60)
    const hh = String(h).padStart(2, '0')
    const mm = String(m).padStart(2, '0')
    const ss = String(s).padStart(2, '0')
    castStore.seek(`${hh}:${mm}:${ss}`)
  }
}

function togglePlayPause() {
  if (castStore.isPlaying) {
    castStore.pauseCast()
  } else {
    castStore.resumeCast()
  }
}

function getStatusLabel() {
  switch (castStore.castState.status) {
    case 'connecting': return t('cast.connecting')
    case 'playing': return t('cast.playing')
    case 'paused': return t('cast.paused')
    case 'error': return t('cast.error')
    default: return t('cast.idle')
  }
}
</script>

<template>
  <div v-if="castStore.isCasting" class="cast-control">
    <!-- Top: status + media title -->
    <div class="cast-control__header">
      <div class="cast-control__info">
        <div class="cast-control__status">
          <span class="cast-control__dot" :class="`cast-control__dot--${castStore.castState.status}`" />
          {{ getStatusLabel() }}
        </div>
        <span v-if="castStore.castState.media" class="cast-control__media">
          {{ castStore.castState.media.title }}
        </span>
      </div>
    </div>

    <!-- Progress bar (video/audio only) -->
    <div v-if="isPlayable && canSeek" class="cast-control__progress">
      <span class="cast-control__time">{{ displayPosition }}</span>
      <div class="cast-control__slider-wrap">
        <div class="cast-control__track">
          <div class="cast-control__fill" :style="{ width: displayProgress + '%' }" />
        </div>
        <input
          type="range"
          class="cast-control__slider"
          min="0"
          max="100"
          step="0.5"
          :value="displayProgress"
          @input="onSliderInput"
          @mousedown="onSliderMouseDown"
          @mouseup="onSliderMouseUp"
          @touchstart.passive="onSliderMouseDown"
          @touchend="onSliderMouseUp"
        />
      </div>
      <span class="cast-control__time">{{ displayDuration }}</span>
    </div>

    <!-- Controls: video/audio — full playback controls -->
    <div v-if="isPlayable" class="cast-control__actions">
      <button
        class="cast-control__btn cast-control__btn--play"
        @click="togglePlayPause"
        :title="castStore.isPlaying ? t('cast.pause') : t('cast.play')"
      >
        <!-- Pause icon -->
        <svg v-if="castStore.isPlaying" width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <rect x="3" y="2" width="4" height="12" rx="1" />
          <rect x="9" y="2" width="4" height="12" rx="1" />
        </svg>
        <!-- Play icon -->
        <svg v-else width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path d="M4 2.5v11l9-5.5L4 2.5z" />
        </svg>
      </button>
      <button
        class="cast-control__btn cast-control__btn--stop"
        @click="castStore.stopCast()"
        :disabled="castStore.loading"
      >
        {{ t('cast.stop') }}
      </button>
    </div>

    <!-- Controls: image — close only -->
    <div v-else-if="isImage" class="cast-control__actions">
      <button
        class="cast-control__btn cast-control__btn--stop"
        @click="castStore.stopCast()"
        :disabled="castStore.loading"
      >
        {{ t('cast.closeImage') }}
      </button>
    </div>

    <!-- Controls: unknown type — stop only -->
    <div v-else class="cast-control__actions">
      <button
        class="cast-control__btn cast-control__btn--stop"
        @click="castStore.stopCast()"
        :disabled="castStore.loading"
      >
        {{ t('cast.stop') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.cast-control {
  display: flex;
  flex-direction: column;
  gap: var(--sp-sm);
  padding: var(--sp-md) var(--sp-lg);
  margin: 0 var(--sp-md);
  background: var(--primary-light);
  border-radius: var(--r-lg);
  border: 1px solid var(--primary);
}

/* ── Header ── */
.cast-control__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.cast-control__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}

.cast-control__status {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
}

.cast-control__dot {
  width: 8px;
  height: 8px;
  border-radius: var(--r-full);
  flex-shrink: 0;
}

.cast-control__dot--connecting {
  background: var(--status-busy);
  animation: pulse 1.5s infinite;
}

.cast-control__dot--playing {
  background: var(--status-online);
}

.cast-control__dot--paused {
  background: var(--status-busy);
}

.cast-control__dot--error {
  background: #EF4444;
}

.cast-control__media {
  font-size: 12px;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Progress ── */
.cast-control__progress {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
}

.cast-control__time {
  font-size: 11px;
  font-variant-numeric: tabular-nums;
  color: var(--text-secondary);
  min-width: 36px;
  text-align: center;
  user-select: none;
}

.cast-control__slider-wrap {
  position: relative;
  flex: 1;
  height: 20px;
  display: flex;
  align-items: center;
}

.cast-control__track {
  position: absolute;
  left: 0;
  right: 0;
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
  pointer-events: none;
}

.cast-control__fill {
  height: 100%;
  background: var(--primary);
  border-radius: 2px;
  transition: width 0.3s linear;
}

.cast-control__slider {
  position: relative;
  width: 100%;
  height: 20px;
  margin: 0;
  opacity: 0;
  cursor: pointer;
  -webkit-appearance: none;
  appearance: none;
}

.cast-control__slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px;
  height: 12px;
}

/* ── Actions ── */
.cast-control__actions {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-sm);
}

.cast-control__btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.cast-control__btn--play {
  width: 32px;
  height: 32px;
  border-radius: var(--r-full);
  background: var(--primary);
  color: white;
}

.cast-control__btn--play:hover {
  background: var(--primary-hover);
}

.cast-control__btn--stop {
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 500;
  color: #EF4444;
  border: 1px solid #EF4444;
  border-radius: var(--r-full);
  white-space: nowrap;
  background: transparent;
}

.cast-control__btn--stop:hover:not(:disabled) {
  background: #EF4444;
  color: white;
}

.cast-control__btn--stop:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
