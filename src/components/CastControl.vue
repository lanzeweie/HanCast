<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useCastStore } from '@/stores/cast'

const { t } = useI18n()
const castStore = useCastStore()

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
    <div class="cast-control__info">
      <div class="cast-control__status">
        <span class="cast-control__dot" :class="`cast-control__dot--${castStore.castState.status}`" />
        {{ getStatusLabel() }}
      </div>
      <span v-if="castStore.castState.media" class="cast-control__media">
        {{ castStore.castState.media.title }}
      </span>
    </div>
    <button class="cast-control__stop" @click="castStore.stopCast()" :disabled="castStore.loading">
      {{ t('cast.stop') }}
    </button>
  </div>
</template>

<style scoped>
.cast-control {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-md) var(--sp-lg);
  margin: 0 var(--sp-md);
  background: var(--primary-light);
  border-radius: var(--r-lg);
  border: 1px solid var(--primary);
}

.cast-control__info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
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

.cast-control__stop {
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 500;
  color: #EF4444;
  border: 1px solid #EF4444;
  border-radius: var(--r-full);
  white-space: nowrap;
  flex-shrink: 0;
  transition: all var(--transition-fast);
}

.cast-control__stop:hover:not(:disabled) {
  background: #EF4444;
  color: white;
}

.cast-control__stop:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
</style>
