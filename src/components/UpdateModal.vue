<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useUpdateStore } from '@/stores/update'
import Modal from './Modal.vue'
import DownloadModal from './DownloadModal.vue'

const { t } = useI18n()
const updateStore = useUpdateStore()
const showDownloadModal = ref(false)

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
  showDownloadModal.value = true
}

function onDownloadClose() {
  showDownloadModal.value = false
}
</script>

<template>
  <Modal :visible="isVisible" @close="onClose">
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
  <DownloadModal :visible="showDownloadModal" @close="onDownloadClose" />
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
