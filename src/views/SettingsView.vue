<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore, type ThemeMode } from '@/stores/theme'
import { useGuardStore } from '@/stores/guard'
import { useUpdateStore } from '@/stores/update'
import GuardDeviceList from '@/components/GuardDeviceList.vue'
import CustomSelect from '@/components/CustomSelect.vue'
import Modal from '@/components/Modal.vue'
import { exportLogs, getFirewallStatus, openFirewallSettings } from '@/api/commands'
import { isMacOS } from '@/utils/platform'
import type { Protocol } from '@/types/settings'
import type { FirewallStatus } from '@/types/firewall'

const router = useRouter()
const { t, locale } = useI18n()
const settingsStore = useSettingsStore()
const themeStore = useThemeStore()
const guardStore = useGuardStore()
const updateStore = useUpdateStore()

const friendlyName = ref('')
const showGuardDevices = ref(false)

// 投屏协议：选中后先弹确认，确认才写入配置并触发热重载
const protocol = ref<Protocol>('dlna')
const pendingProtocol = ref<Protocol | null>(null)

onMounted(async () => {
  await settingsStore.fetchSettings()
  friendlyName.value = settingsStore.settings.friendly_name
  protocol.value = settingsStore.settings.protocol ?? 'dlna'
  refreshFirewall()
})

// ── macOS 防火墙状态与指引 ──
const firewall = ref<FirewallStatus | null>(null)
const firewallError = ref(false)

async function refreshFirewall() {
  if (!isMacOS) return
  try {
    firewall.value = await getFirewallStatus()
    firewallError.value = false
  } catch {
    firewallError.value = true
  }
}

async function onOpenFirewall() {
  try {
    await openFirewallSettings()
  } catch {
    // 打开失败不影响设置页其他操作
  }
}

const firewallText = computed(() => {
  const fw = firewall.value
  if (!fw || !fw.supported || firewallError.value) return t('settings.firewallUnknown')
  if (fw.blockAll) return t('settings.firewallBlockAll')
  return fw.enabled ? t('settings.firewallEnabled') : t('settings.firewallDisabled')
})

const firewallTone = computed(() => {
  const fw = firewall.value
  if (!fw || !fw.supported || firewallError.value) return 'unknown'
  return fw.enabled ? 'warn' : 'ok'
})

function protocolLabel(value: Protocol): string {
  return value === 'dlna' ? t('settings.protocolDlna') : t('settings.protocolNva')
}

function onProtocolSelect(value: string | number) {
  const next = value as Protocol
  if (next === protocol.value) return
  pendingProtocol.value = next
}

async function confirmProtocol() {
  const next = pendingProtocol.value
  pendingProtocol.value = null
  if (!next) return
  const prev = protocol.value
  protocol.value = next
  // 后端写入失败（或拒绝）时回滚，避免界面显示的协议与实际身份不一致
  if (!(await settingsStore.saveSettings({ protocol: next }))) {
    protocol.value = prev
  }
}

function cancelProtocol() {
  pendingProtocol.value = null
}

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

function onGuardTimeoutChange(timeout: number | string) {
  guardStore.saveSettings({ confirm_timeout: Number(timeout) })
}

function toggleGuardDevices() {
  showGuardDevices.value = !showGuardDevices.value
  if (showGuardDevices.value) {
    guardStore.fetchDevices()
  }
}

const checkUpdateStatus = ref<'idle' | 'checking' | 'no_update' | 'error'>('idle')
const exportLogsStatus = ref<'idle' | 'done' | 'error'>('idle')

async function onExportLogs() {
  try {
    const ok = await exportLogs()
    if (ok) {
      exportLogsStatus.value = 'done'
      setTimeout(() => { exportLogsStatus.value = 'idle' }, 2000)
    }
  } catch {
    exportLogsStatus.value = 'error'
    setTimeout(() => { exportLogsStatus.value = 'idle' }, 2000)
  }
}

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
    <header
      class="settings__header"
      :class="{ 'settings__header--mac': isMacOS }"
      :data-tauri-drag-region="isMacOS ? 'deep' : undefined"
    >
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
          <CustomSelect
            :model-value="themeStore.mode"
            @update:model-value="onThemeChange($event as ThemeMode)"
            :options="[
              { label: t('theme.system'), value: 'system' },
              { label: t('theme.light'), value: 'light' },
              { label: t('theme.dark'), value: 'dark' },
            ]"
          />
        </div>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.language') }}</span>
          <CustomSelect
            :model-value="locale"
            @update:model-value="onLanguageChange($event as string)"
            :options="[
              { label: '简体中文', value: 'zh-CN' },
              { label: 'English', value: 'en-US' },
            ]"
          />
        </div>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.autoStart') }}</span>
          <label class="settings__toggle">
            <input
              type="checkbox"
              :checked="settingsStore.autostart"
              @change="settingsStore.toggleAutostart()"
            />
            <span class="settings__toggle-slider" />
          </label>
        </div>

        <p v-if="isMacOS" class="settings__hint">
          {{ t('settings.autoStartHintMac') }}
        </p>
      </section>

      <!-- Cast -->
      <section class="settings__section">
        <h3 class="settings__section-title">{{ t('settings.cast') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.protocol') }}</span>
          <CustomSelect
            :model-value="protocol"
            @update:model-value="onProtocolSelect"
            :options="[
              { label: t('settings.protocolDlna'), value: 'dlna' },
              { label: t('settings.protocolNva'), value: 'nva' },
            ]"
          />
        </div>

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
          <CustomSelect
            :model-value="guardStore.settings.confirm_timeout"
            @update:model-value="onGuardTimeoutChange"
            :options="[
              { label: t('guard.seconds', { n: 10 }), value: 10 },
              { label: t('guard.seconds', { n: 15 }), value: 15 },
              { label: t('guard.seconds', { n: 30 }), value: 30 },
              { label: t('guard.seconds', { n: 60 }), value: 60 },
            ]"
          />
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

      <!-- Network (macOS firewall guidance) -->
      <section v-if="isMacOS" class="settings__section">
        <h3 class="settings__section-title">{{ t('settings.network') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.firewall') }}</span>
          <span class="settings__status" :class="`settings__status--${firewallTone}`">
            {{ firewallText }}
          </span>
        </div>

        <p class="settings__hint">{{ t('settings.firewallHint') }}</p>

        <button class="settings__item settings__item--clickable" @click="onOpenFirewall">
          <span class="settings__label">{{ t('settings.openFirewall') }}</span>
          <svg
            class="settings__chevron"
            viewBox="0 0 24 24" width="16" height="16" fill="none"
            stroke="currentColor" stroke-width="2"
          >
            <polyline points="9 6 15 12 9 18" />
          </svg>
        </button>
      </section>

      <!-- About -->
      <section class="settings__section">
        <h3 class="settings__section-title">{{ t('settings.about') }}</h3>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.version') }}</span>
          <span class="settings__value">{{ settingsStore.settings.version }}</span>
        </div>

        <div class="settings__item">
          <span class="settings__label">{{ t('settings.exportLogs') }}</span>
          <button class="settings__link" @click="onExportLogs">
            <span v-if="exportLogsStatus === 'done'" class="settings__check-result">✓</span>
            <span v-else-if="exportLogsStatus === 'error'" class="settings__check-result settings__check-result--error">✕</span>
            <span v-else>{{ t('common.saveAs') }}</span>
          </button>
        </div>

        <div class="settings__item">
          <template v-if="updateStore.storeVersion">
            <a
              class="settings__link"
              href="https://apps.microsoft.com/detail/9nk1xwpg6hd5?launch=true&mode=mini"
              target="_blank"
            >
              {{ t('update.storeHint') }}
            </a>
          </template>
          <template v-else>
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
          </template>
        </div>

        <div class="settings__item">
          <a class="settings__link" href="https://github.com/lanzeweie/HanCast" target="_blank">
            {{ t('settings.repository') }}
          </a>
        </div>

        <div class="settings__item">
          <a class="settings__link" href="https://qm.qq.com/q/ihWd29FR0A?group=821473246" target="_blank">
            {{ t('settings.qqGroup') }}
          </a>
        </div>

        <div class="settings__item">
          <a class="settings__link" href="https://github.com/lanzeweie/HanCast?tab=GPL-3.0-1-ov-file#" target="_blank">
            {{ t('settings.license') }}
          </a>
        </div>
      </section>
    </div>
  </div>

  <!-- 协议切换确认 -->
  <Modal
    size="small"
    :visible="pendingProtocol !== null"
    :title="t('settings.protocolConfirmTitle')"
    @close="cancelProtocol"
  >
    <p class="settings__protocol-confirm">
      {{ t('settings.protocolConfirm', { name: pendingProtocol ? protocolLabel(pendingProtocol) : '' }) }}
    </p>
    <template #actions>
      <button class="btn-cancel" @click="cancelProtocol">{{ t('common.cancel') }}</button>
      <button class="btn-confirm" @click="confirmProtocol">{{ t('common.confirm') }}</button>
    </template>
  </Modal>
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

.settings__header--mac {
  -webkit-app-region: no-drag;
  /* 给原生红绿灯留出位置 */
  padding-left: 78px;
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

.settings__hint {
  font-size: 11px;
  line-height: 1.6;
  color: var(--text-tertiary);
  padding: 0 var(--sp-md);
  margin: 0;
}

.settings__status {
  font-size: 13px;
  font-weight: 600;
}

.settings__status--ok {
  color: var(--status-online);
}

.settings__status--warn {
  color: var(--status-busy);
}

.settings__status--unknown {
  color: var(--text-tertiary);
}

.settings__value--mono {
  font-family: 'SF Mono', 'Consolas', monospace;
  font-size: 12px;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* select styles moved to CustomSelect.vue */

.settings__input {
  padding: 4px 8px;
  font-size: 13px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-primary);
  width: 180px;
}

.settings__input--small {
  width: 80px;
}

.settings__input:focus {
  border-color: var(--border-focus);
}

.settings__protocol-confirm {
  white-space: pre-line;
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
