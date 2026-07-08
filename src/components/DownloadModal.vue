<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import Modal from './Modal.vue'

const { t } = useI18n()

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

const GITHUB_URL = 'https://github.com/lanzeweie/HanCast/releases/latest'
const GITEE_URL = 'https://gitee.com/buxiangqumingzi/han-cast/releases/latest'

async function openUrl(url: string) {
  try {
    const { open } = await import('@tauri-apps/plugin-shell')
    await open(url)
  } catch {
    // Fallback for browser dev
    window.open(url, '_blank')
  }
}

function onGithub() {
  openUrl(GITHUB_URL)
  emit('close')
}

function onGitee() {
  openUrl(GITEE_URL)
  emit('close')
}
</script>

<template>
  <Modal :visible="visible" :show-icon="false" @close="emit('close')">
    <div class="download-content">
      <div class="download-title">{{ t('update.chooseSource') }}</div>
      <div class="download-options">
        <button class="btn-github" @click="onGithub">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M12 0c-6.626 0-12 5.373-12 12 0 5.302 3.438 9.8 8.207 11.387.599.111.793-.261.793-.577v-2.234c-3.338.726-4.033-1.416-4.033-1.416-.546-1.387-1.333-1.756-1.333-1.756-1.089-.745.083-.729.083-.729 1.205.084 1.839 1.237 1.839 1.237 1.07 1.834 2.807 1.304 3.492.997.107-.775.418-1.305.762-1.604-2.665-.305-5.467-1.334-5.467-5.931 0-1.311.469-2.381 1.236-3.221-.124-.303-.535-1.524.117-3.176 0 0 1.008-.322 3.301 1.23.957-.266 1.983-.399 3.003-.404 1.02.005 2.047.138 3.006.404 2.291-1.552 3.297-1.23 3.297-1.23.653 1.653.242 2.874.118 3.176.77.84 1.235 1.911 1.235 3.221 0 4.609-2.807 5.624-5.479 5.921.43.372.823 1.102.823 2.222v3.293c0 .319.192.694.801.576 4.765-1.589 8.199-6.086 8.199-11.386 0-6.627-5.373-12-12-12z"/>
          </svg>
          <span>GitHub</span>
        </button>
        <button class="btn-gitee" @click="onGitee">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor">
            <path d="M12 0C5.37 0 0 5.37 0 12s5.37 12 12 12 12-5.37 12-12S18.63 0 12 0zm5.95 14.14H9.37c-2.13 0-3.94-1.74-3.94-3.88 0-2.13 1.81-3.88 3.94-3.88h6.58c.55 0 1 .45 1 1s-.45 1-1 1H9.37c-1.07 0-1.94.87-1.94 1.88 0 1 .87 1.88 1.94 1.88h6.58c.55 0 1 .45 1 1s-.45 1-1 1z"/>
          </svg>
          <span>Gitee</span>
        </button>
      </div>
    </div>

    <template #actions>
      <button class="btn-cancel" @click="emit('close')">{{ t('common.cancel') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.download-content {
  text-align: center;
}

.download-title {
  font-size: 14px;
  color: var(--text-primary);
  margin-bottom: 16px;
}

.download-options {
  display: flex;
  gap: 12px;
  justify-content: center;
}

.download-options button {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  border-radius: 8px;
  transition: all 0.2s;
  font-family: var(--font);
}

.btn-github {
  background: #24292f;
  color: white;
}

.btn-github:hover {
  background: #374151;
}

.btn-gitee {
  background: #c71d23;
  color: white;
}

.btn-gitee:hover {
  background: #dc2626;
}
</style>
