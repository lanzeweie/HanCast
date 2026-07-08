<script setup lang="ts">
import { onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { useGuardStore } from '@/stores/guard'
import GuardConfirmModal from '@/components/GuardConfirmModal.vue'

const settingsStore = useSettingsStore()
const themeStore = useThemeStore()
const guardStore = useGuardStore()

onMounted(() => {
  settingsStore.fetchSettings()
})
</script>

<template>
  <router-view />
  <!-- Guard modal: always mounted, works on any page -->
  <GuardConfirmModal />
</template>

<style>
/* Global styles are imported via main.ts */
</style>
