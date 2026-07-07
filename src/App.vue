<script setup lang="ts">
import { onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'

const settingsStore = useSettingsStore()
const themeStore = useThemeStore()

onMounted(() => {
  settingsStore.fetchSettings()
})
</script>

<template>
  <router-view />
</template>

<style>
/* Global styles are imported via main.ts */
</style>
