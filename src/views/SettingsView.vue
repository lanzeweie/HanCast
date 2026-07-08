<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import { useGuardStore } from '@/stores/guard'
import { useUpdateStore } from '@/stores/update'
import GuardDeviceList from '@/components/GuardDeviceList.vue'

const router = useRouter()
const { t, locale } = useI18n()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()
const guardStore = useGuardStore()
const updateStore = useUpdateStore()

const friendlyName = ref('')
const showGuardDevices = ref(false)

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

function onThemeChange(mode: ThemeMode) {
  themeStore.apply(mode)
}

async function saveFriendlyName() {
  await settingsStore.saveSettings({ friendly_name: friendlyName.value })
}

function onGuardEnabledChange(e: Event) {
  const enabled = (e.target as HTMLInputElement).checked
  guardStore.saveSettings({ enabled })
}

function onGuardTimeoutChange(e: Event) {
  const timeout = Number((e.target as HTMLSelectElement).value)
  guardStore.saveSettings({ confirm_timeout: timeout })
}

function toggleGuardDevices() {
  showGuardDevices.value = !showGuardDevices.value
  if (showGuardDevices.value) {
    guardStore.fetchDevices()
  }
}

const checkUpdateStatus = ref<'idle' | 'checking' | 'no_update' | 'error'>('idle')

async function onCheckUpdate() {
  checkUpdateStatus.value = 'checking'
  const result = await updateStore.check(settingsStore.settings.version, true)
  if (result?.has_update) {
    checkUpdateStatus.value = 'idle' // modal will show
  } else if (result && !result.has_update) {
    checkUpdateStatus.value = 'no_update'
    setTimeout(() => { checkUpdateStatus.value = 'idle' }, 2000)
  } else {
    checkUpdateStatus.value = 'error'
    setTimeout(() => { checkUpdateStatus.value = 'idle' }, 2000)
  }
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
          <span class="settings__label">{{ t('theme.title') }}</span>
          <select
            class="settings__select"
            :value="themeStore.mode"
            @change="onThemeChange(($event.target as HTMLSelectElement).value as ThemeMode)"
          >
            <option value="system">{{ t('theme.system') }}</option>
            <option value="light">{{ t('theme.light') }}</option>
            <option value="dark">{{ t('theme.dark') }}</option>
          </select>
        </div>

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

      <!-- Cast Security (Device Guard) -->
      <section class="settings__section">
        <h3 class="settings__section-title">{{ t('guard.title') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('guard.enable') }}</span>
          <label class="settings__toggle">
            <input
              type="checkbox"
              :checked="guardStore.settings.enabled"
              @change="onGuardEnabledChange"
            />
            <span class="settings__toggle-slider" />
          </label>
        </div>

        <div class="settings__item">
          <span class="settings__label">{{ t('guard.timeout') }}</span>
          <select
            class="settings__select"
            :value="guardStore.settings.confirm_timeout"
            @change="onGuardTimeoutChange"
            :disabled="!guardStore.settings.enabled"
          >
            <option :value="10">{{ t('guard.seconds', { n: 10 }) }}</option>
            <option :value="15">{{ t('guard.seconds', { n: 15 }) }}</option>
            <option :value="30">{{ t('guard.seconds', { n: 30 }) }}</option>
            <option :value="60">{{ t('guard.seconds', { n: 60 }) }}</option>
          </select>
        </div>

        <button class="settings__item settings__item--clickable" @click="toggleGuardDevices">
          <span class="settings__label">
            {{ t('guard.trusted') }}
            <span v-if="guardStore.trustedDevices.length" class="settings__badge">
              {{ guardStore.trustedDevices.length }}
            </span>
          </span>
          <svg
            class="settings__chevron"
            :class="{ 'settings__chevron--open': showGuardDevices }"
            viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2"
          >
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </button>

        <Transition name="settings-expand">
          <div v-if="showGuardDevices" class="settings__guard-list">
            <GuardDeviceList />
          </div>
        </Transition>
      </section>

      <!-- About -->
      <section class="settings__section">
        <h3 class="settings__section-title">{{ t('settings.about') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.version') }}</span>
          <span class="settings__value">{{ settingsStore.settings.version }}</span>
        </div>

        <div class="settings__item">
          <button
            class="settings__link"
            :disabled="checkUpdateStatus === 'checking'"
            @click="onCheckUpdate"
          >
            <span v-if="checkUpdateStatus === 'checking'">{{ t('update.checking') }}</span>
            <span v-else-if="checkUpdateStatus === 'no_update'" class="settings__check-result">{{ t('update.latestAlready') }}</span>
            <span v-else-if="checkUpdateStatus === 'error'" class="settings__check-result settings__check-result--error">{{ t('update.checkFailed') }}</span>
            <span v-else>{{ t('settings.checkUpdate') }}</span>
          </button>
        </div>

        <div class="settings__item">
          <a class="settings__link" href="https://github.com/lanzeweie/HanCast?tab=GPL-3.0-1-ov-file#" target="_blank">
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

.settings__link:disabled {
  opacity: 0.6;
  cursor: not-allowed;
  text-decoration: none;
}

.settings__check-result {
  font-size: 12px;
  color: var(--text-tertiary);
}

.settings__check-result--error {
  color: #EF4444;
}

/* ── Toggle switch ── */
.settings__toggle {
  position: relative;
  display: inline-block;
  width: 40px;
  height: 22px;
  cursor: pointer;
}

.settings__toggle input {
  opacity: 0;
  width: 0;
  height: 0;
}

.settings__toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--border);
  border-radius: var(--r-full);
  transition: background var(--transition-fast);
}

.settings__toggle-slider::before {
  content: '';
  position: absolute;
  width: 18px;
  height: 18px;
  left: 2px;
  bottom: 2px;
  background: white;
  border-radius: 50%;
  transition: transform var(--transition-fast);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
}

.settings__toggle input:checked + .settings__toggle-slider {
  background: var(--primary);
}

.settings__toggle input:checked + .settings__toggle-slider::before {
  transform: translateX(18px);
}

/* ── Clickable item ── */
.settings__item--clickable {
  cursor: pointer;
  transition: background var(--transition-fast);
}

.settings__item--clickable:hover {
  background: var(--bg-secondary);
}

/* ── Badge ── */
.settings__badge {
  font-size: 11px;
  padding: 1px 6px;
  background: var(--primary-light);
  color: var(--primary);
  border-radius: var(--r-full);
  font-weight: 600;
  margin-left: var(--sp-xs);
}

/* ── Chevron ── */
.settings__chevron {
  color: var(--text-tertiary);
  transition: transform var(--transition-fast);
  flex-shrink: 0;
}

.settings__chevron--open {
  transform: rotate(180deg);
}

/* ── Guard list expand ── */
.settings__guard-list {
  overflow: hidden;
}

.settings-expand-enter-active,
.settings-expand-leave-active {
  transition: all var(--transition-normal);
  max-height: 500px;
}

.settings-expand-enter-from,
.settings-expand-leave-to {
  opacity: 0;
  max-height: 0;
}
</style>
