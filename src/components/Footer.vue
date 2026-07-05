<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useDeviceStore } from '@/stores/device'

const { t } = useI18n()
const deviceStore = useDeviceStore()
</script>

<template>
  <footer v-if="deviceStore.devices.length === 0" class="footer">
    <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
      <circle cx="12" cy="12" r="10" />
      <path d="M12 16v-4M12 8h.01" />
    </svg>
    <span>{{ t('footer.noDevice') }}</span>
  </footer>
</template>

<style scoped>
.footer {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  padding: var(--sp-md) var(--sp-lg);
  font-size: 12px;
  color: var(--text-tertiary);
  text-align: center;
  justify-content: center;
  flex-shrink: 0;
}
</style>
