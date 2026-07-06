<script setup lang="ts">
const props = defineProps<{
  visible: boolean
  title?: string
}>()

const emit = defineEmits<{
  (e: 'close'): void
}>()

function onOverlay(e: MouseEvent) {
  if ((e.target as HTMLElement).classList.contains('modal-overlay')) {
    emit('close')
  }
}
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="visible" class="modal-overlay" @click="onOverlay">
        <div class="modal-box">
          <div v-if="title" class="modal-title">{{ title }}</div>
          <div class="modal-body">
            <slot />
          </div>
          <div class="modal-actions">
            <slot name="actions" />
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}

.modal-box {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-xl);
  padding: var(--sp-xl);
  min-width: 280px;
  max-width: 360px;
  box-shadow: var(--shadow-lg);
}

.modal-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: var(--sp-md);
}

.modal-body {
  font-size: 13px;
  color: var(--text-secondary);
  margin-bottom: var(--sp-xl);
}

.modal-body input {
  width: 100%;
  padding: var(--sp-sm) var(--sp-md);
  font-size: 13px;
  color: var(--text-primary);
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  outline: none;
  transition: border-color var(--transition-fast);
  font-family: var(--font);
}

.modal-body input:focus {
  border-color: var(--border-focus);
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--sp-sm);
}

.modal-actions :slotted(button) {
  padding: var(--sp-sm) var(--sp-lg);
  font-size: 13px;
  font-weight: 500;
  border-radius: var(--r-md);
  transition: all var(--transition-fast);
  font-family: var(--font);
}

.modal-actions :slotted(button.btn-cancel) {
  color: var(--text-secondary);
  background: var(--bg-secondary);
}

.modal-actions :slotted(button.btn-cancel:hover) {
  background: var(--border);
}

.modal-actions :slotted(button.btn-confirm) {
  color: white;
  background: var(--primary);
}

.modal-actions :slotted(button.btn-confirm:hover) {
  background: var(--primary-hover);
}

.modal-actions :slotted(button.btn-danger) {
  color: white;
  background: #EF4444;
}

.modal-actions :slotted(button.btn-danger:hover) {
  background: #DC2626;
}

/* transition */
.modal-enter-active,
.modal-leave-active {
  transition: opacity var(--transition-normal);
}
.modal-enter-active .modal-box,
.modal-leave-active .modal-box {
  transition: transform var(--transition-normal);
}
.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}
.modal-enter-from .modal-box {
  transform: scale(0.95);
}
.modal-leave-to .modal-box {
  transform: scale(0.95);
}
</style>
