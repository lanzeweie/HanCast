<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useDeviceStore } from '@/stores/device'
import DeviceCard from './DeviceCard.vue'

const { t } = useI18n()
const deviceStore = useDeviceStore()
</script>

<template>
  <div class="device-list">
    <div class="device-list__header">
      <div class="device-list__title">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
          <rect x="2" y="3" width="20" height="14" rx="2" />
          <path d="M8 21h8M12 17v4" />
        </svg>
        <span>{{ t('devices.title') }}</span>
      </div>
      <button class="device-list__refresh" @click="deviceStore.refresh()" :disabled="deviceStore.loading">
        <svg
          viewBox="0 0 24 24"
          width="16"
          height="16"
          fill="none"
          stroke="currentColor"
          stroke-width="2"
          :class="{ 'spinning': deviceStore.loading }"
        >
          <path d="M23 4v6h-6M1 20v-6h6" />
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15" />
        </svg>
      </button>
    </div>

    <div class="device-list__items" v-if="deviceStore.devices.length > 0">
      <DeviceCard
        v-for="device in deviceStore.devices"
        :key="device.id"
        :device="device"
      />
    </div>

    <div v-else class="device-list__empty">
      <p>{{ t('devices.offline') }}</p>
    </div>
  </div>
</template>

<style scoped>
.device-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.device-list__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-lg);
  margin-bottom: var(--sp-md);
}

.device-list__title {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.device-list__refresh {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-sm);
  color: var(--text-secondary);
  transition: all var(--transition-fast);
}

.device-list__refresh:hover:not(:disabled) {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.device-list__refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.spinning {
  animation: spin 1s linear infinite;
}

.device-list__items {
  display: flex;
  flex-direction: column;
  gap: var(--sp-sm);
  padding: 0 var(--sp-md);
  overflow-y: auto;
  flex: 1;
}

.device-list__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--sp-2xl);
  color: var(--text-tertiary);
  font-size: 13px;
}
</style>
