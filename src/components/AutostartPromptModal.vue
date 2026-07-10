<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settings'
import Modal from './Modal.vue'

const { t } = useI18n()
const settingsStore = useSettingsStore()

const props = defineProps<{
  visible: boolean
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

async function onEnable() {
  await settingsStore.toggleAutostart()
  markAsked()
  emit('close')
}

function onSkip() {
  markAsked()
  emit('close')
}

function markAsked() {
  localStorage.setItem('has_asked_autostart', 'true')
}
</script>

<template>
  <Modal :visible="visible" size="small" :title="t('autostartPrompt.title')" @close="onSkip">
    <div class="autostart-prompt">
      <p class="autostart-prompt__desc">
        {{ t('autostartPrompt.desc') }}
      </p>
      <p class="autostart-prompt__hint">
        {{ t('autostartPrompt.hint') }}
      </p>
    </div>

    <template #actions>
      <button class="btn-cancel" @click="onSkip">{{ t('autostartPrompt.skip') }}</button>
      <button class="btn-confirm" @click="onEnable">{{ t('autostartPrompt.enable') }}</button>
    </template>
  </Modal>
</template>

<style scoped>
.autostart-prompt__desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.6;
  text-align: left;
  margin: 0 0 var(--sp-sm) 0;
}

.autostart-prompt__hint {
  font-size: 11px;
  color: var(--text-tertiary);
  line-height: 1.5;
  text-align: left;
  margin: 0;
}
</style>
