<script setup lang="ts">
import { useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { minimizeWindow, closeWindow } from '@/api/commands'

const router = useRouter()
const { t } = useI18n()

function goToSettings() {
  router.push('/settings')
}
</script>

<template>
  <header class="title-bar">
    <div class="title-bar__left">
      <svg class="title-bar__logo" viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2">
        <rect x="2" y="3" width="20" height="14" rx="2" />
        <path d="M8 21h8M12 17v4" />
      </svg>
      <span class="title-bar__title">{{ t('app.title') }}</span>
    </div>

    <div class="title-bar__right">
      <button class="title-bar__btn" @click="goToSettings" :title="t('settings.title')">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12.22 2h-.44a2 2 0 00-2 2v.18a2 2 0 01-1 1.73l-.43.25a2 2 0 01-2 0l-.15-.08a2 2 0 00-2.73.73l-.22.38a2 2 0 00.73 2.73l.15.1a2 2 0 011 1.72v.51a2 2 0 01-1 1.74l-.15.09a2 2 0 00-.73 2.73l.22.38a2 2 0 002.73.73l.15-.08a2 2 0 012 0l.43.25a2 2 0 011 1.73V20a2 2 0 002 2h.44a2 2 0 002-2v-.18a2 2 0 011-1.73l.43-.25a2 2 0 012 0l.15.08a2 2 0 002.73-.73l.22-.39a2 2 0 00-.73-2.73l-.15-.08a2 2 0 01-1-1.74v-.5a2 2 0 011-1.74l.15-.09a2 2 0 00.73-2.73l-.22-.38a2 2 0 00-2.73-.73l-.15.08a2 2 0 01-2 0l-.43-.25a2 2 0 01-1-1.73V4a2 2 0 00-2-2z" />
          <circle cx="12" cy="12" r="3" />
        </svg>
      </button>
      <button class="title-bar__btn" @click="minimizeWindow" :title="'Minimize'">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M5 12h14" />
        </svg>
      </button>
      <button class="title-bar__btn title-bar__btn--close" @click="closeWindow" :title="'Close'">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M18 6L6 18M6 6l12 12" />
        </svg>
      </button>
    </div>
  </header>
</template>

<style scoped>
.title-bar {
  height: var(--titlebar-height);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--sp-md);
  -webkit-app-region: drag;
  user-select: none;
  flex-shrink: 0;
}

.title-bar__left {
  display: flex;
  align-items: center;
  gap: var(--sp-sm);
}

.title-bar__logo {
  color: var(--primary);
  flex-shrink: 0;
}

.title-bar__title {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
}

.title-bar__right {
  display: flex;
  align-items: center;
  gap: 2px;
  -webkit-app-region: no-drag;
}

.title-bar__btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--r-sm);
  color: var(--text-secondary);
  transition: background var(--transition-fast), color var(--transition-fast);
}

.title-bar__btn:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.title-bar__btn--close:hover {
  background: #EF4444;
  color: white;
}
</style>
