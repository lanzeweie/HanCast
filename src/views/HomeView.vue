<script setup lang="ts">
import TitleBar from '@/components/TitleBar.vue'
import MediaInput from '@/components/MediaInput.vue'
import DeviceList from '@/components/DeviceList.vue'
import CastController from '@/components/CastController.vue'
import Footer from '@/components/Footer.vue'
import AutostartPromptModal from '@/components/AutostartPromptModal.vue'
import { useCastStore } from '@/stores/cast'
import { storeToRefs } from 'pinia'

const castStore = useCastStore()
const { showAutostartPrompt } = storeToRefs(castStore)
</script>

<template>
  <div class="home">
    <TitleBar />
    <main class="home__content">
      <MediaInput />
      <DeviceList />
    </main>
    <Footer />
    <!-- Embedded cast controller modal -->
    <CastController />
    <!-- Autostart prompt (first successful cast) -->
    <AutostartPromptModal
      :visible="showAutostartPrompt"
      @close="castStore.closeAutostartPrompt()"
    />
  </div>
</template>

<style scoped>
.home {
  display: flex;
  flex-direction: column;
  height: 100%;
  background: var(--bg-primary);
}

.home__content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: var(--sp-lg);
  padding: var(--sp-lg) 0;
  overflow: hidden;
  min-height: 0;
}
</style>
