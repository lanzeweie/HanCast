<script setup lang="ts">
import { ref, computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useGuardStore } from '@/stores/guard'
import type { GuardDevice } from '@/types/guard'

const { t } = useI18n()
const guardStore = useGuardStore()

const activeTab = ref<'trusted' | 'blacklisted'>('trusted')

const devices = computed(() =>
  activeTab.value === 'trusted'
    ? guardStore.trustedDevices
    : guardStore.blacklistedDevices,
)

function formatDate(iso: string): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleDateString()
}

function onRemove(device: GuardDevice) {
  const key = device.udn || device.ip
  guardStore.removeDevice(key)
}

function onSwitchPolicy(device: GuardDevice) {
  const key = device.udn || device.ip
  const newPolicy = activeTab.value === 'trusted' ? 'blacklisted' : 'trusted'
  guardStore.setPolicy(key, newPolicy)
}
</script>

<template>
  <div class="guard-list">
    <!-- Tabs -->
    <div class="guard-list__tabs">
      <button
        class="guard-list__tab"
        :class="{ 'guard-list__tab--active': activeTab === 'trusted' }"
        @click="activeTab = 'trusted'"
      >
        {{ t('guard.trusted') }}
        <span v-if="guardStore.trustedDevices.length" class="guard-list__count">
          {{ guardStore.trustedDevices.length }}
        </span>
      </button>
      <button
        class="guard-list__tab"
        :class="{ 'guard-list__tab--active': activeTab === 'blacklisted' }"
        @click="activeTab = 'blacklisted'"
      >
        {{ t('guard.blacklisted') }}
        <span v-if="guardStore.blacklistedDevices.length" class="guard-list__count">
          {{ guardStore.blacklistedDevices.length }}
        </span>
      </button>
    </div>

    <!-- Device list -->
    <div class="guard-list__items" v-if="devices.length > 0">
      <div
        v-for="device in devices"
        :key="device.udn || device.ip"
        class="guard-list__item"
      >
        <div class="guard-list__item-info">
          <div class="guard-list__item-name">{{ device.friendly_name }}</div>
          <div class="guard-list__item-detail">
            <span>{{ device.ip }}</span>
            <span class="guard-list__item-sep">·</span>
            <span>{{ t('guard.castCount', { n: device.cast_count }) }}</span>
          </div>
          <div class="guard-list__item-date">
            {{ t('guard.firstTrusted', { date: formatDate(device.created_at) }) }}
          </div>
        </div>

        <div class="guard-list__item-actions">
          <button
            class="guard-list__item-btn"
            @click="onSwitchPolicy(device)"
            :title="activeTab === 'trusted' ? t('guard.moveToBlacklist') : t('guard.moveToTrusted')"
          >
            <svg v-if="activeTab === 'trusted'" viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
            <svg v-else viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
              <polyline points="9 12 11 14 15 10" />
            </svg>
          </button>
          <button
            class="guard-list__item-btn guard-list__item-btn--danger"
            @click="onRemove(device)"
            :title="t('guard.remove')"
          >
            <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18" />
              <line x1="6" y1="6" x2="18" y2="18" />
            </svg>
          </button>
        </div>
      </div>
    </div>

    <!-- Empty state -->
    <div v-else class="guard-list__empty">
      {{ activeTab === 'trusted' ? t('guard.noTrusted') : t('guard.noBlacklisted') }}
    </div>
  </div>
</template>

<style scoped>
.guard-list {
  background: var(--bg-card);
  border-radius: var(--r-lg);
  overflow: hidden;
}

/* ── Tabs ── */
.guard-list__tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
}

.guard-list__tab {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--sp-xs);
  padding: var(--sp-sm) var(--sp-md);
  font-size: 13px;
  font-weight: 500;
  color: var(--text-tertiary);
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.guard-list__tab:hover {
  color: var(--text-secondary);
}

.guard-list__tab--active {
  color: var(--primary);
  border-bottom-color: var(--primary);
}

.guard-list__count {
  font-size: 11px;
  padding: 1px 6px;
  background: var(--primary-light);
  color: var(--primary);
  border-radius: var(--r-full);
  font-weight: 600;
}

/* ── Items ── */
.guard-list__items {
  display: flex;
  flex-direction: column;
}

.guard-list__item {
  display: flex;
  align-items: center;
  gap: var(--sp-md);
  padding: var(--sp-md) var(--sp-lg);
  border-bottom: 1px solid var(--border);
}

.guard-list__item:last-child {
  border-bottom: none;
}

.guard-list__item-info {
  flex: 1;
  min-width: 0;
}

.guard-list__item-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.guard-list__item-detail {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

.guard-list__item-sep {
  margin: 0 4px;
}

.guard-list__item-date {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 2px;
}

/* ── Item actions ── */
.guard-list__item-actions {
  display: flex;
  gap: var(--sp-xs);
  flex-shrink: 0;
}

.guard-list__item-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-sm);
  color: var(--text-tertiary);
  background: none;
  border: none;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.guard-list__item-btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.guard-list__item-btn--danger:hover {
  background: rgba(239, 68, 68, 0.1);
  color: #EF4444;
}

/* ── Empty ── */
.guard-list__empty {
  padding: var(--sp-xl);
  text-align: center;
  font-size: 13px;
  color: var(--text-tertiary);
}
</style>
