import { ref, computed } from 'vue'
import { defineStore } from 'pinia'

export type ThemeMode = 'system' | 'light' | 'dark'

const STORAGE_KEY = 'hancast-theme'

function getSystemTheme(): 'light' | 'dark' {
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
}

function resolve(mode: ThemeMode): 'light' | 'dark' {
  return mode === 'system' ? getSystemTheme() : mode
}

function persist(mode: ThemeMode) {
  document.documentElement.setAttribute('data-theme', resolve(mode))
  localStorage.setItem(STORAGE_KEY, mode)
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>((localStorage.getItem(STORAGE_KEY) as ThemeMode) || 'system')

  /** Actual visual theme (resolves 'system' to light/dark) */
  const applied = computed(() => resolve(mode.value))

  function apply(m: ThemeMode) {
    mode.value = m
    persist(m)
  }

  /** Title bar: flip current visual, set mode to explicit light/dark */
  function toggle() {
    apply(applied.value === 'dark' ? 'light' : 'dark')
  }

  // Apply on init
  persist(mode.value)

  // Listen for system theme changes when in 'system' mode
  const mq = window.matchMedia('(prefers-color-scheme: dark)')
  mq.addEventListener('change', () => {
    if (mode.value === 'system') {
      document.documentElement.setAttribute('data-theme', getSystemTheme())
    }
  })

  return { mode, applied, apply, toggle }
})
