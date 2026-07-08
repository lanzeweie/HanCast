import { ref, onMounted, onUnmounted } from 'vue'
import { defineStore } from 'pinia'
import type { UpdateInfo } from '@/api/commands'
import { checkUpdate, ignoreUpdateVersion as apiIgnoreUpdateVersion } from '@/api/commands'
import type { UnlistenFn } from '@tauri-apps/api/event'

export const useUpdateStore = defineStore('update', () => {
  // ── State ──
  const updateInfo = ref<UpdateInfo | null>(null)
  const showModal = ref(false)
  const loading = ref(false)
  const error = ref('')

  let unlistenFns: UnlistenFn[] = []
  let listenersSetup = false

  // ── Actions ──

  /** 手动检查更新（设置页按钮调用） */
  async function check(currentVersion: string, force = true) {
    loading.value = true
    error.value = ''
    try {
      const result = await checkUpdate(currentVersion, force)
      if (result.has_update) {
        updateInfo.value = result
        showModal.value = true
      } else {
        // 没有更新，或被忽略 —— 手动检查时可以给个提示
        if (force) {
          error.value = 'no_update' // 用于 UI 提示"已是最新版本"
        }
      }
      return result
    } catch (e) {
      error.value = String(e)
      return null
    } finally {
      loading.value = false
    }
  }

  /** 用户选择"此版本不再提示" */
  async function ignoreVersion() {
    if (!updateInfo.value) return
    try {
      await apiIgnoreUpdateVersion(updateInfo.value.latest)
    } catch (e) {
      console.error('Failed to ignore update version:', e)
    }
    closeModal()
  }

  /** 关闭弹窗 */
  function closeModal() {
    showModal.value = false
  }

  /** 前往下载页 */
  function openDownload() {
    if (updateInfo.value?.url) {
      window.open(updateInfo.value.url, '_blank')
    }
    closeModal()
  }

  // ── Event listeners (auto-check from Rust) ──

  async function setupListeners() {
    if (listenersSetup) return
    listenersSetup = true

    try {
      const { listen } = await import('@tauri-apps/api/event')

      // Rust 启动时自动检查，发现更新后 emit 此事件
      const unlisten = await listen<UpdateInfo>('update-available', (event) => {
        updateInfo.value = event.payload
        showModal.value = true
      })
      unlistenFns.push(unlisten)
    } catch {
      // Not in Tauri environment — ignore
    }
  }

  function cleanup() {
    unlistenFns.forEach((fn) => fn())
    unlistenFns = []
    listenersSetup = false
  }

  // ── Lifecycle ──

  onMounted(() => {
    setupListeners()
  })

  onUnmounted(() => {
    cleanup()
  })

  return {
    updateInfo,
    showModal,
    loading,
    error,
    check,
    ignoreVersion,
    closeModal,
    openDownload,
  }
})
