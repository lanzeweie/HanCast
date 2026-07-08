<script setup lang="ts">
import { onMounted } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import { useThemeStore } from '@/stores/theme'
import { useGuardStore } from '@/stores/guard'
import { useUpdateStore } from '@/stores/update'
import GuardConfirmModal from '@/components/GuardConfirmModal.vue'
import UpdateModal from '@/components/UpdateModal.vue'

const settingsStore = useSettingsStore()
const themeStore = useThemeStore()
const guardStore = useGuardStore()
const updateStore = useUpdateStore()

onMounted(() => {
  settingsStore.fetchSettings()
})
</script>

<template>
  <router-view />
  <!-- Guard modal: always mounted, works on any page -->
  <GuardConfirmModal />
  <!-- Update modal: always mounted, listens for update-available event -->
  <UpdateModal />
</template>

<style>
/* Global styles are imported via main.ts */
</style>
