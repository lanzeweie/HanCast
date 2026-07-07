<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settings'

const router = useRouter()
const { t, locale } = useI18n()
const settingsStore = useSettingsStore()

const friendlyName = ref('')

onMounted(async () => {
  await settingsStore.fetchSettings()
  friendlyName.value = settingsStore.settings.friendly_name
})

function goBack() {
  router.push('/')
}

function onLanguageChange(lang: string) {
  locale.value = lang
}

async function saveFriendlyName() {
  await settingsStore.saveSettings({ friendly_name: friendlyName.value })
}
</script>

<template>
  <div class="settings">
    <header class="settings__header">
      <button class="settings__back" @click="goBack">
        <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M19 12H5M12 19l-7-7 7-7" />
        </svg>
      </button>
      <span class="settings__title">{{ t('settings.title') }}</span>
    </header>

    <div class="settings__body">
      <!-- General -->
      <section class="settings__section">
        <h3 class="settings__section-title">{{ t('settings.general') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.language') }}</span>
          <select
            class="settings__select"
            :value="locale"
            @change="onLanguageChange(($event.target as HTMLSelectElement).value)"
          >
            <option value="zh-CN">简体中文</option>
            <option value="en-US">English</option>
          </select>
        </div>
      </section>

      <!-- Cast -->
      <section class="settings__section">
        <h3 class="settings__section-title">{{ t('settings.cast') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.dlnaName') }}</span>
          <input
            class="settings__input"
            type="text"
            v-model="friendlyName"
            @blur="saveFriendlyName"
          />
        </div>

      </section>

      <!-- About -->
      <section class="settings__section">
        <h3 class="settings__section-title">{{ t('settings.about') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.version') }}</span>
          <span class="settings__value">{{ settingsStore.settings.version }}</span>
        </div>

        <div class="settings__item">
          <button class="settings__link">{{ t('settings.checkUpdate') }}</button>
        </div>

        <div class="settings__item">
          <a class="settings__link" href="https://github.com/xfangfang/Macast" target="_blank">
            {{ t('settings.license') }}
          </a>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.settings {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.settings__header {
  height: var(--titlebar-height);
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
  padding: 0 var(--sp-md);
  -webkit-app-region: drag;
  flex-shrink: 0;
}

.settings__back {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-sm);
  color: var(--text-secondary);
  -webkit-app-region: no-drag;
  transition: all var(--transition-fast);
}

.settings__back:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.settings__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  -webkit-app-region: no-drag;
}

.settings__body {
  flex: 1;
  overflow-y: auto;
  padding: var(--sp-md) var(--sp-lg);
  display: flex;
  flex-direction: column;
  gap: var(--sp-lg);
}

.settings__section {
  display: flex;
  flex-direction: column;
  gap: var(--sp-sm);
}

.settings__section-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-tertiary);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  padding-bottom: var(--sp-xs);
}

.settings__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--sp-sm) var(--sp-md);
  background: var(--bg-card);
  border-radius: var(--r-md);
}

.settings__label {
  font-size: 14px;
  color: var(--text-primary);
}

.settings__value {
  font-size: 14px;
  color: var(--text-secondary);
}

.settings__value--mono {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.settings__select {
  padding: 4px 8px;
  font-size: 13px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-primary);
  cursor: pointer;
}

.settings__input {
  padding: 4px 8px;
  font-size: 13px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-primary);
  width: 160px;
}

.settings__input--small {
  width: 80px;
}

.settings__input:focus {
  border-color: var(--border-focus);
}

.settings__link {
  font-size: 14px;
  color: var(--text-link);
  background: none;
  border: none;
  cursor: pointer;
  padding: 0;
}

.settings__link:hover {
  text-decoration: underline;
}
</style>
