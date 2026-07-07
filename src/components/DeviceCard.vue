<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Device } from '@/types/device'
import { useDeviceStore } from '@/stores/device'
import { useMediaStore } from '@/stores/media'
import { useCastStore } from '@/stores/cast'
import Modal from './Modal.vue'

const props = defineProps({
  device: {
    type: Object as () => Device,
    required: true,
  },
})

const { t } = useI18n()
const deviceStore = useDeviceStore()
const mediaStore = useMediaStore()
const castStore = useCastStore()

const showMenu = ref(false)
const menuWrapRef = ref<HTMLElement | null>(null)

// Modal states
const showRename = ref(false)
const showRemove = ref(false)
const renameInput = ref('')

// ── Casting state for this device ──
const isCastingToDevice = computed(() => {
  return castStore.isCasting && castStore.castState.device_id === props.device.id
})

const castingTitle = computed(() => {
  const title = castStore.castState.media?.title ?? ''
  return title.length > 15 ? title.slice(0, 15) + '...' : title
})

function onDocClick(e: MouseEvent) {
  if (showMenu.value && menuWrapRef.value && !menuWrapRef.value.contains(e.target as Node)) {
    showMenu.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocClick))
onUnmounted(() => document.removeEventListener('click', onDocClick))

function getStatusColor(status: string) {
  switch (status) {
    case 'online': return 'var(--status-online)'
    case 'busy': return 'var(--status-busy)'
    default: return 'var(--status-offline)'
  }
}

function isOnline() {
  return props.device.status === 'online'
}

function isOffline() {
  return props.device.status === 'offline'
}

function onCast() {
  if (!isOnline() || !mediaStore.mediaInfo) return
  castStore.startCast(props.device.id, mediaStore.mediaInfo.uri, {
    title: mediaStore.mediaInfo.title,
    mime_type: mediaStore.mediaInfo.mime_type,
    thumbnail: mediaStore.mediaInfo.thumbnail,
  })
}

async function onRestoreController() {
  if (isCastingToDevice.value) {
    castStore.restoreController()
  }
}

function onSetDefault() {
  deviceStore.setDefault(props.device.id)
  showMenu.value = false
}

function onRenameClick() {
  renameInput.value = props.device.name
  showRename.value = true
  showMenu.value = false
}

function onRenameConfirm() {
  if (renameInput.value.trim()) {
    deviceStore.rename(props.device.id, renameInput.value.trim())
  }
  showRename.value = false
}

function onRemoveClick() {
  showRemove.value = true
  showMenu.value = false
}

function onRemoveConfirm() {
  deviceStore.hide(props.device.id)
  showRemove.value = false
}

function toggleMenu() {
  showMenu.value = !showMenu.value
}
</script>

<template>
  <div
    class="device-card"
    :class="{
      'device-card--offline': isOffline(),
      'device-card--casting': isCastingToDevice,
    }"
  >
    <span class="device-card__status" :style="{ background: getStatusColor(device.status) }" />

    <div class="device-card__info">
      <div class="device-card__name-row">
        <span class="device-card__name" :class="{ 'device-card__name--offline': isOffline() }">
          {{ device.name }}
        </span>
        <span v-if="device.is_default" class="device-card__badge">{{ t('devices.defaultBadge') }}</span>
      </div>
      <div class="device-card__ip">{{ device.ip }}</div>
    </div>

    <!-- Multi-room sync (for speakers) -->
    <label v-if="device.type === 'speaker' && isOnline()" class="device-card__sync">
      <input type="checkbox" checked disabled />
      <span>{{ t('devices.multiRoomSync') }}</span>
      <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="var(--text-tertiary)" stroke-width="2">
        <circle cx="12" cy="12" r="10" />
        <path d="M12 16v-4M12 8h.01" />
      </svg>
    </label>

    <div class="device-card__actions">
      <!-- Casting: truncated video title + window icon -->
      <template v-if="isCastingToDevice">
        <span class="device-card__casting-name">{{ castingTitle }}</span>
        <button
          class="device-card__window-icon"
          @click.stop="onRestoreController"
          :title="t('devices.restoreController')"
        >
          <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.5">
            <rect x="2" y="3" width="20" height="14" rx="2" />
            <path d="M8 21h8M12 17v4" />
          </svg>
        </button>
      </template>

      <!-- Normal cast button -->
      <button
        v-if="isOnline() && !isCastingToDevice"
        class="device-card__cast"
        @click="onCast"
        :disabled="!mediaStore.isReady || castStore.loading"
      >
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M2 16.1A5 5 0 015.9 20M2 12.05A9 9 0 019.95 20M2 8V6a2 2 0 012-2h16a2 2 0 012 2v12a2 2 0 01-2 2h-6" />
          <circle cx="2" cy="20" r="1" fill="currentColor" />
        </svg>
        {{ t('devices.cast') }}
      </button>

      <span v-if="!isOnline() && !isCastingToDevice" class="device-card__na">{{ t('devices.notApplicable') }}</span>

      <div class="device-card__menu-wrap" ref="menuWrapRef">
        <button class="device-card__more" @click="toggleMenu">
          <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
            <circle cx="12" cy="5" r="1.5" />
            <circle cx="12" cy="12" r="1.5" />
            <circle cx="12" cy="19" r="1.5" />
          </svg>
        </button>

        <div v-if="showMenu" class="device-card__menu">
          <button @click="onSetDefault">{{ t('devices.setDefault') }}</button>
          <button @click="onRenameClick">{{ t('devices.rename') }}</button>
          <button class="device-card__menu--danger" @click="onRemoveClick">{{ t('devices.remove') }}</button>
        </div>
      </div>
    </div>

    <!-- Rename Modal -->
    <Modal :visible="showRename" :title="t('devices.rename')" @close="showRename = false">
      <input
        v-model="renameInput"
        :placeholder="t('devices.rename')"
        @keydown.enter="onRenameConfirm"
        autofocus
      />
      <template #actions>
        <button class="btn-cancel" @click="showRename = false">{{ t('common.cancel') }}</button>
        <button class="btn-confirm" @click="onRenameConfirm">{{ t('common.confirm') }}</button>
      </template>
    </Modal>

    <!-- Remove Confirm Modal -->
    <Modal :visible="showRemove" :title="t('devices.remove')" @close="showRemove = false">
      <p>{{ t('devices.removeConfirm', { name: device.name }) }}</p>
      <template #actions>
        <button class="btn-cancel" @click="showRemove = false">{{ t('common.cancel') }}</button>
        <button class="btn-danger" @click="onRemoveConfirm">{{ t('common.confirm') }}</button>
      </template>
    </Modal>
  </div>
</template>

<style scoped>
.device-card {
  display: flex;
  align-items: center;
  gap: var(--sp-md);
  padding: var(--sp-md) var(--sp-lg);
  background: var(--bg-card);
  border-radius: var(--r-lg);
  transition: background var(--transition-fast);
  position: relative;
}

.device-card:hover {
  background: var(--bg-secondary);
}

.device-card--offline {
  opacity: 0.6;
}

.device-card__status {
  width: 8px;
  height: 8px;
  border-radius: var(--r-full);
  flex-shrink: 0;
}

.device-card__info {
  flex: 1;
  min-width: 0;
}

.device-card__name-row {
  display: flex;
  align-items: center;
  gap: var(--sp-xs);
}

.device-card__name {
  font-size: 14px;
  font-weight: 500;
  color: var(--text-primary);
}

.device-card__name--offline {
  color: var(--text-tertiary);
}

.device-card__ip {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 1px;
}

.device-card__badge {
  font-size: 10px;
  padding: 1px 6px;
  background: var(--primary-light);
  color: var(--primary);
  border-radius: var(--r-full);
  font-weight: 500;
}

.device-card__sync {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
  cursor: default;
  flex-shrink: 0;
}

.device-card__sync input[type="checkbox"] {
  accent-color: var(--primary);
  width: 14px;
  height: 14px;
}

.device-card__actions {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  flex-shrink: 0;
}

.device-card__cast {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--primary);
  border: 1px solid var(--primary);
  border-radius: var(--r-full);
  transition: all var(--transition-fast);
}

.device-card__cast:hover:not(:disabled) {
  background: var(--primary);
  color: white;
}

.device-card__cast:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.device-card__na {
  font-size: 12px;
  color: var(--text-tertiary);
}

.device-card__menu-wrap {
  position: relative;
}

.device-card__more {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-sm);
  color: var(--text-tertiary);
  transition: all var(--transition-fast);
}

.device-card__more:hover {
  background: var(--border);
  color: var(--text-primary);
}

.device-card__menu {
  position: absolute;
  right: 0;
  top: 100%;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  padding: var(--sp-xs) 0;
  min-width: 140px;
  box-shadow: var(--shadow-lg);
  z-index: 10;
  animation: fadeIn 0.15s ease;
}

.device-card__menu button {
  width: 100%;
  text-align: left;
  padding: var(--sp-sm) var(--sp-md);
  font-size: 13px;
  color: var(--text-primary);
  transition: background var(--transition-fast);
}

.device-card__menu button:hover {
  background: var(--bg-secondary);
}

.device-card__menu--danger {
  color: #EF4444 !important;
}

/* ── Casting state ── */
.device-card--casting {
  background: linear-gradient(135deg, var(--bg-card), rgba(251, 191, 36, 0.1));
  border: 1px solid rgba(251, 191, 36, 0.3);
}

.device-card__casting-name {
  font-size: 11px;
  font-weight: 500;
  color: #D97706;
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-card__window-icon {
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 10px;
  color: #B45309;
  background: rgba(251, 191, 36, 0.2);
  cursor: pointer;
  transition: all var(--transition-fast);
  animation: pulse-icon 2s ease-in-out infinite;
}

.device-card__window-icon:hover {
  background: rgba(251, 191, 36, 0.35);
  transform: scale(1.08);
}

@keyframes pulse-icon {
  0%, 100% {
    box-shadow: 0 0 0 0 rgba(245, 158, 11, 0.5);
  }
  50% {
    box-shadow: 0 0 0 8px rgba(245, 158, 11, 0);
  }
}
</style>
