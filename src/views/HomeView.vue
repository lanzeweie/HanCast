<script setup lang="ts">
import TitleBar from '@/components/TitleBar.vue'
import MediaInput from '@/components/MediaInput.vue'
import DeviceList from '@/components/DeviceList.vue'
import CastControl from '@/components/CastControl.vue'
import Footer from '@/components/Footer.vue'
</script>

<template>
  <div class="home">
    <TitleBar />
    <main class="home__content">
      <MediaInput />
      <CastControl />
      <DeviceList />
    </main>
    <Footer />
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
