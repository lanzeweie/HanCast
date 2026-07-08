<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useGuardStore } from '@/stores/guard'

const { t } = useI18n()
const guardStore = useGuardStore()

const request = computed(() => guardStore.pendingRequest)
const isVisible = computed(() => !!request.value)
const device = computed(() => request.value?.device)

function onReject() {
  guardStore.handleResponse(false, 'reject')
}

function onOnce() {
  guardStore.handleResponse(true, 'once')
}

function onAlways() {
  guardStore.handleResponse(true, 'always')
}
</script>

<template>
  <Teleport to="body">
    <Transition name="guard-fade">
      <div v-if="isVisible" class="guard-overlay" @click.self>
        <div class="guard-modal">

          <!-- Header -->
          <div class="guard__header">
            <span class="guard__title">{{ t('guard.newDevice') }}</span>
            <div class="guard__header-right">
              <span class="guard__countdown-text">
                <strong>{{ guardStore.countdown }}</strong> 秒
                <span class="guard__countdown-sub">后自动拒绝</span>
              </span>
              <button class="guard__close" @click="onReject" :title="t('guard.reject')">
                <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                  <line x1="18" y1="6" x2="6" y2="18" />
                  <line x1="6" y1="6" x2="18" y2="18" />
                </svg>
              </button>
            </div>
          </div>

          <!-- Device icon -->
          <div class="guard__icon-area">
            <div class="guard__icon-circle">
              <svg viewBox="0 0 24 24" width="40" height="40" fill="none" stroke="#5B9BF5" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
                <rect x="2" y="3" width="20" height="14" rx="2" />
                <path d="M8 21h8M12 17v4" />
              </svg>
              <div class="guard__icon-badge">?</div>
            </div>
          </div>

          <!-- Device info -->
          <div class="guard__device" v-if="device">
            <div class="guard__device-name">{{ device.friendly_name || t('guard.unknownDevice') }}</div>
            <div class="guard__device-detail">
              {{ t('guard.fromLocal') }} · {{ device.ip }}
            </div>
            <div class="guard__prompt">{{ t('guard.prompt') }}</div>
          </div>

          <!-- Action buttons -->
          <div class="guard__actions">
            <button class="guard__btn guard__btn--reject" @click="onReject">
              {{ t('guard.reject') }}
            </button>
            <button class="guard__btn guard__btn--once" @click="onOnce">
              {{ t('guard.allowOnce') }}
            </button>
            <button class="guard__btn guard__btn--always" @click="onAlways">
              {{ t('guard.always') }}
            </button>
          </div>

        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
/* ── Overlay ── */
.guard-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
}

/* ── Modal ── */
.guard-modal {
  width: 340px;
  background: var(--bg-card);
  border-radius: 20px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.2);
  overflow: hidden;
  font-family: var(--font);
  padding: 24px 24px 20px;
}

/* ── Header ── */
.guard__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 20px;
}

.guard__title {
  font-size: 17px;
  font-weight: 700;
  color: var(--text-primary);
  line-height: 1.4;
}

.guard__header-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ── Countdown text ── */
.guard__countdown-text {
  font-size: 13px;
  color: var(--primary);
  white-space: nowrap;
  background: var(--primary-light);
  padding: 4px 10px;
  border-radius: var(--r-full);
}

.guard__countdown-text strong {
  font-size: 15px;
  font-weight: 700;
}

.guard__countdown-sub {
  color: var(--text-tertiary);
  font-size: 11px;
}

/* ── Close button ── */
.guard__close {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 50%;
  background: transparent;
  color: var(--text-tertiary);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.guard__close:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

/* ── Device icon area ── */
.guard__icon-area {
  display: flex;
  justify-content: center;
  margin-bottom: 16px;
}

.guard__icon-circle {
  position: relative;
  width: 88px;
  height: 88px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #EBF3FE;
  border-radius: 50%;
}

.guard__icon-badge {
  position: absolute;
  bottom: 4px;
  right: 4px;
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: white;
  border: 2px solid #EBF3FE;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 700;
  color: var(--text-tertiary);
}

/* ── Device info ── */
.guard__device {
  text-align: center;
  margin-bottom: 24px;
}

.guard__device-name {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 6px;
}

.guard__device-detail {
  font-size: 13px;
  color: var(--text-tertiary);
  margin-bottom: 12px;
}

.guard__prompt {
  font-size: 13px;
  color: var(--text-secondary);
}

/* ── Actions ── */
.guard__actions {
  display: flex;
  gap: 10px;
}

.guard__btn {
  flex: 1;
  padding: 11px 0;
  font-size: 14px;
  font-weight: 600;
  border: none;
  border-radius: var(--r-md);
  cursor: pointer;
  transition: all var(--transition-fast);
  font-family: var(--font);
}

.guard__btn--reject {
  color: var(--text-secondary);
  background: var(--bg-secondary);
  border: 1px solid var(--border);
}
.guard__btn--reject:hover {
  background: var(--border);
  color: var(--text-primary);
}

.guard__btn--once {
  color: var(--primary);
  background: var(--primary-light);
}
.guard__btn--once:hover {
  background: rgba(59, 130, 246, 0.15);
}

.guard__btn--always {
  color: white;
  background: #3B82F6;
}
.guard__btn--always:hover {
  background: #2563EB;
}

/* ── Transition ── */
.guard-fade-enter-active,
.guard-fade-leave-active {
  transition: opacity 0.2s ease;
}
.guard-fade-enter-active .guard-modal,
.guard-fade-leave-active .guard-modal {
  transition: transform 0.2s ease, opacity 0.2s ease;
}
.guard-fade-enter-from,
.guard-fade-leave-to {
  opacity: 0;
}
.guard-fade-enter-from .guard-modal {
  transform: scale(0.95) translateY(8px);
}
.guard-fade-leave-to .guard-modal {
  transform: scale(0.95) translateY(8px);
}

/* ── Dark mode ── */
[data-theme="dark"] .guard__icon-circle {
  background: rgba(99, 102, 241, 0.15);
}
[data-theme="dark"] .guard__icon-badge {
  background: var(--bg-card);
  border-color: rgba(99, 102, 241, 0.15);
}
[data-theme="dark"] .guard__btn--always {
  background: #6366F1;
}
[data-theme="dark"] .guard__btn--always:hover {
  background: #4F46E5;
}
</style>
