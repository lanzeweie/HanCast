<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
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

// 非 dev 模式下禁用浏览器默认右键菜单
function onContextMenu(e: MouseEvent) {
  e.preventDefault()
}

onMounted(() => {
  settingsStore.fetchSettings()
  if (!import.meta.env.DEV) {
    document.addEventListener('contextmenu', onContextMenu)
  }
})

onUnmounted(() => {
  document.removeEventListener('contextmenu', onContextMenu)
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
