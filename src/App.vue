<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'

const settingsStore = useSettingsStore()
const theme = ref<'light' | 'dark'>('light')

onMounted(() => {
  // Detect system theme preference
  const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches
  theme.value = prefersDark ? 'dark' : 'light'
  document.documentElement.setAttribute('data-theme', theme.value)

  // Listen for system theme changes
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
    theme.value = e.matches ? 'dark' : 'light'
    document.documentElement.setAttribute('data-theme', theme.value)
  })

  settingsStore.fetchSettings()
})
</script>

<template>
  <router-view />
</template>

<style>
/* Global styles are imported via main.ts */
</style>
