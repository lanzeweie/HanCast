<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useCastStore } from '@/stores/cast'
import { useDeviceStore } from '@/stores/device'

const { t } = useI18n()
const castStore = useCastStore()
const deviceStore = useDeviceStore()

// ── Device ──
const currentDevice = computed(() => {
  const id = castStore.castState.device_id
  if (!id) return null
  return deviceStore.devices.find(d => d.id === id) ?? null
})
const deviceName = computed(() => currentDevice.value?.name ?? '—')

// ── Media type ──
const mediaMimeType = computed(() => {
  let mime = castStore.castState.media?.mime_type ?? ''
  if (!mime) {
    const uri = castStore.castState.media?.uri ?? ''
    const ext = uri.split('.').pop()?.toLowerCase() ?? ''
    const map: Record<string, string> = {
      mp4: 'video/mp4', mkv: 'video/x-matroska', avi: 'video/x-msvideo',
      mov: 'video/quicktime', webm: 'video/webm', flv: 'video/x-flv',
      mp3: 'audio/mpeg', flac: 'audio/flac', wav: 'audio/wav',
      aac: 'audio/aac', ogg: 'audio/ogg', m4a: 'audio/mp4',
      jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png',
      gif: 'image/gif', webp: 'image/webp', bmp: 'image/bmp',
    }
    mime = map[ext] ?? ''
  }
  return mime
})
const isImage = computed(() => mediaMimeType.value.startsWith('image/'))
const isPlayable = computed(() => mediaMimeType.value.startsWith('video/') || mediaMimeType.value.startsWith('audio/'))

// ── Media title ──
const mediaTitle = computed(() => castStore.castState.media?.title ?? '')

// ── Preview ──
let convertFileSrc: ((path: string, protocol?: string) => string) | null = null
const previewUrl = computed(() => {
  const info = castStore.castState.media
  if (!info?.uri) return null
  if (convertFileSrc && !info.uri.startsWith('http')) return convertFileSrc(info.uri)
  if (info.uri.startsWith('http')) return info.uri
  return null
})

// ── Playback ──
const isPlaying = computed(() => castStore.castState.status === 'playing')

async function togglePlayPause() {
  if (isPlaying.value) await castStore.pauseCast()
  else await castStore.resumeCast()
}

// ── Volume ──
let _invoke: ((cmd: string, args?: any) => Promise<any>) | null = null
async function setVolume(e: Event) {
  const v = Number((e.target as HTMLInputElement).value)
  if (!_invoke) {
    _invoke = (await import('@tauri-apps/api/core')).invoke
  }
  await _invoke('set_volume', { volume: v })
}

onMounted(async () => {
  if (window.__TAURI_INTERNALS__) {
    try { convertFileSrc = (await import('@tauri-apps/api/core')).convertFileSrc } catch {}
  }
})
</script>

<template>
  <Teleport to="body">
    <Transition name="ctrl-fade">
      <div v-if="castStore.showController" class="ctrl-overlay" @click.self="castStore.minimizeController()">
        <div class="ctrl-modal">

          <!-- Header -->
          <div class="ctrl__head">
            <div class="ctrl__title">{{ t('controller.controlling') }}：{{ deviceName }}</div>
            <button class="ctrl__min" @click="castStore.minimizeController()" :title="t('controller.minimize')">
              <svg viewBox="0 0 12 12" width="12" height="12" fill="none" stroke="currentColor" stroke-width="1.5"><line x1="2" y1="6" x2="10" y2="6"/></svg>
            </button>
          </div>

          <!-- Image mode: only stop -->
          <template v-if="isImage">
            <button class="ctrl__stop" @click="castStore.stopCast()" :disabled="castStore.loading">
              {{ t('cast.stop') }}
            </button>
          </template>

          <!-- Video/audio mode: full controls -->
          <template v-else>
            <!-- Thumbnail -->
            <div class="ctrl__thumb">
              <img v-if="previewUrl" :src="previewUrl" class="ctrl__thumb-img" :alt="mediaTitle" />
              <div v-else class="ctrl__thumb-ph">
                <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="currentColor" stroke-width="1.5" opacity=".2">
                  <rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>
                </svg>
              </div>
            </div>

            <!-- Filename -->
            <div class="ctrl__name">{{ mediaTitle }}</div>

            <!-- Volume -->
            <div class="ctrl__vol">
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <path d="M15.54 8.46a5 5 0 010 7.07M19.07 4.93a10 10 0 010 14.14"/>
              </svg>
              <input type="range" class="ctrl__vol-bar" min="0" max="100"
                :value="castStore.castState.is_muted ? 0 : castStore.castState.volume"
                @input.stop="setVolume" />
              <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <path d="M15.54 8.46a5 5 0 010 7.07M19.07 4.93a10 10 0 010 14.14"/>
              </svg>
            </div>

            <!-- Playback -->
            <div class="ctrl__pb">
              <button class="ctrl__pb-btn" disabled>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><polygon points="19 20 9 12 19 4 19 20"/><line x1="5" y1="19" x2="5" y2="5" stroke="currentColor" stroke-width="2"/></svg>
              </button>
              <button class="ctrl__pb-btn ctrl__pb-main" @click="togglePlayPause">
                <svg v-if="isPlaying" viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/></svg>
                <svg v-else viewBox="0 0 24 24" width="24" height="24" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              </button>
              <button class="ctrl__pb-btn" disabled>
                <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor"><polygon points="5 4 15 12 5 20 5 4"/><line x1="19" y1="5" x2="19" y2="19" stroke="currentColor" stroke-width="2"/></svg>
              </button>
            </div>

            <!-- Stop -->
            <button class="ctrl__stop" @click="castStore.stopCast()" :disabled="castStore.loading">
              {{ t('cast.stop') }}
            </button>
          </template>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ── Overlay ── */
.ctrl-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

/* ── Modal ── */
.ctrl-modal {
  width: 240px;
  background: rgba(248, 248, 248, 0.95);
  backdrop-filter: blur(20px);
  -webkit-backdrop-filter: blur(20px);
  border-radius: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 0;
  overflow: hidden;
  font-family: var(--font);
  user-select: none;
}

/* ── Header ── */
.ctrl__head {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 12px 6px;
}

.ctrl__title {
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.ctrl__min {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: background 0.15s;
}
.ctrl__min:hover { background: rgba(0,0,0,.08); }

/* ── Thumbnail ── */
.ctrl__thumb {
  width: calc(100% - 24px);
  aspect-ratio: 16 / 10;
  border-radius: 10px;
  overflow: hidden;
  background: rgba(0,0,0,.04);
  display: flex;
  align-items: center;
  justify-content: center;
  margin: 4px 12px;
}
.ctrl__thumb-img { width: 100%; height: 100%; object-fit: cover; }
.ctrl__thumb-ph { display: flex; align-items: center; justify-content: center; }

/* ── Filename ── */
.ctrl__name {
  font-size: 12px;
  font-weight: 500;
  color: var(--text-primary);
  padding: 2px 12px;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  width: 100%;
}

/* ── Volume ── */
.ctrl__vol {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 12px;
  width: 100%;
  color: var(--text-tertiary);
}
.ctrl__vol-bar {
  flex: 1;
  height: 3px;
  -webkit-appearance: none;
  appearance: none;
  background: #D1D5DB;
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}
.ctrl__vol-bar::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #6B7280;
}

/* ── Playback ── */
.ctrl__pb {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 16px;
  padding: 4px 12px;
}
.ctrl__pb-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  background: transparent;
  color: #374151;
  cursor: pointer;
}
.ctrl__pb-btn:disabled { opacity: .3; cursor: not-allowed; }
.ctrl__pb-main { width: 40px; height: 40px; }

/* ── Stop ── */
.ctrl__stop {
  width: calc(100% - 24px);
  padding: 10px 24px;
  margin: 8px 12px 12px;
  font-size: 14px;
  font-weight: 600;
  color: white;
  background: #EF4444;
  border: none;
  border-radius: 10px;
  cursor: pointer;
  transition: background .15s;
  font-family: var(--font);
}
.ctrl__stop:hover:not(:disabled) { background: #DC2626; }
.ctrl__stop:disabled { opacity: .5; cursor: not-allowed; }

/* ── Transition ── */
.ctrl-fade-enter-active,
.ctrl-fade-leave-active {
  transition: opacity 0.2s ease;
}
.ctrl-fade-enter-active .ctrl-modal,
.ctrl-fade-leave-active .ctrl-modal {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.ctrl-fade-enter-from,
.ctrl-fade-leave-to {
  opacity: 0;
}
.ctrl-fade-enter-from .ctrl-modal {
  transform: scale(0.9);
}
.ctrl-fade-leave-to .ctrl-modal {
  transform: scale(0.9);
}

/* ── Dark mode ── */
@media (prefers-color-scheme: dark) {
  .ctrl-modal { background: rgba(30, 30, 30, 0.95); }
  .ctrl__min:hover { background: rgba(255,255,255,.1); }
  .ctrl__thumb { background: rgba(255,255,255,.05); }
  .ctrl__pb-btn { color: #D1D5DB; }
  .ctrl__vol-bar { background: #4B5563; }
  .ctrl__vol-bar::-webkit-slider-thumb { background: #9CA3AF; }
}
</style>
