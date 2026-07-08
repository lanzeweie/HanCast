<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUpdateStore } from '@/stores/update'
import Modal from './Modal.vue'

const { t } = useI18n()
const updateStore = useUpdateStore()

const isVisible = computed(() => updateStore.showModal && !!updateStore.updateInfo?.has_update)
const info = computed(() => updateStore.updateInfo)

/** 将 markdown changelog 简单转为纯文本摘要 */
const changelogPreview = computed(() => {
  if (!info.value?.body) return ''
  // 去掉 markdown 标记，保留前 300 字符
  return info.value.body
    .replace(/^#+\s*/gm, '')
    .replace(/\*\*/g, '')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim()
    .slice(0, 300)
})

function onIgnore() {
  updateStore.ignoreVersion()
}

function onClose() {
  updateStore.closeModal()
}

function onDownload() {
  updateStore.openDownload()
}
</script>

<template>
  <Modal :visible="isVisible" :title="t('update.title')" :show-icon="true" @close="onClose">
    <template #icon>
      <svg viewBox="0 0 24 24" width="36" height="36" fill="none" stroke="#5B9BF5" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
        <polyline points="7 10 12 15 17 10" />
        <line x1="12" y1="15" x2="12" y2="3" />
      </svg>
    </template>

    <div class="update-content">
      <div class="update-version">
        <span class="update-current">{{ info?.current }}</span>
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14M12 5l7 7-7 7" />
        </svg>
        <span class="update-latest">{{ info?.latest }}</span>
      </div>

      <div v-if="changelogPreview" class="update-changelog">
        <div class="update-changelog-label">{{ t('update.changelog') }}</div>
        <div class="update-changelog-text">{{ changelogPreview }}</div>
      </div>
    </div>

    <template #actions>
      <button class="btn-cancel" @click="onIgnore">{{ t('update.ignoreThisVersion') }}</button>
      <button class="btn-confirm" @click="onDownload">{{ t('update.download') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.update-content {
  text-align: center;
}

.update-version {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-sm);
  margin-bottom: var(--sp-md);
}

.update-current {
  font-size: 14px;
  color: var(--text-secondary);
  padding: 4px 10px;
  background: var(--bg-secondary);
  border-radius: var(--r-sm);
}

.update-latest {
  font-size: 14px;
  font-weight: 600;
  color: var(--primary);
  padding: 4px 10px;
  background: var(--primary-light);
  border-radius: var(--r-sm);
}

.update-version svg {
  color: var(--text-tertiary);
  flex-shrink: 0;
}

.update-changelog {
  text-align: left;
  margin-top: var(--sp-sm);
}

.update-changelog-label {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: var(--sp-xs);
}

.update-changelog-text {
  font-size: 12px;
  color: var(--text-secondary);
  line-height: 1.6;
  max-height: 120px;
  overflow-y: auto;
  padding: var(--sp-sm);
  background: var(--bg-secondary);
  border-radius: var(--r-sm);
  white-space: pre-wrap;
}
</style>
