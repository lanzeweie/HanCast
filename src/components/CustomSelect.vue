<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'

interface Option {
  label: string
  value: string | number
}

const props = defineProps<{
  modelValue: string | number
  options: Option[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string | number]
}>()

const open = ref(false)
const dropdownRef = ref<HTMLElement | null>(null)

const currentLabel = () => {
  return props.options.find(o => o.value === props.modelValue)?.label ?? ''
}

function toggle() {
  open.value = !open.value
}

function select(value: string | number) {
  emit('update:modelValue', value)
  open.value = false
}

function onClickOutside(e: MouseEvent) {
  if (dropdownRef.value && !dropdownRef.value.contains(e.target as Node)) {
    open.value = false
  }
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') open.value = false
}

onMounted(() => {
  document.addEventListener('mousedown', onClickOutside)
  document.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  document.removeEventListener('mousedown', onClickOutside)
  document.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="custom-select" ref="dropdownRef">
    <button class="custom-select__trigger" @click="toggle" type="button">
      <span class="custom-select__value">{{ currentLabel() }}</span>
      <svg
        class="custom-select__arrow"
        :class="{ 'custom-select__arrow--open': open }"
        viewBox="0 0 24 24" width="14" height="14" fill="none"
        stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
      >
        <polyline points="6 9 12 15 18 9" />
      </svg>
    </button>
    <Transition name="select-menu">
      <div v-if="open" class="custom-select__menu">
        <button
          v-for="opt in options"
          :key="String(opt.value)"
          class="custom-select__option"
          :class="{ 'custom-select__option--active': opt.value === modelValue }"
          @click="select(opt.value)"
          type="button"
        >
          {{ opt.label }}
        </button>
      </div>
    </Transition>
  </div>
</template>

<style scoped>
.custom-select {
  position: relative;
}

.custom-select__trigger {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 24px 4px 8px;
  font-size: 13px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: var(--r-sm);
  color: var(--text-primary);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.custom-select__trigger:hover {
  background: var(--bg-secondary);
}

.custom-select__value {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.custom-select__arrow {
  color: var(--text-tertiary);
  transition: transform var(--transition-fast);
  flex-shrink: 0;
  position: absolute;
  right: 6px;
}

.custom-select__arrow--open {
  transform: rotate(180deg);
}

/* ── Dropdown menu ── */
.custom-select__menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 120px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--r-md);
  box-shadow: var(--shadow-md);
  z-index: 100;
  overflow: hidden;
}

.custom-select__option {
  display: block;
  width: 100%;
  padding: 8px 14px;
  font-size: 13px;
  color: var(--text-primary);
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  transition: background var(--transition-fast);
}

.custom-select__option:hover {
  background: var(--bg-secondary);
}

.custom-select__option--active {
  color: var(--primary);
  font-weight: 500;
  background: var(--primary-light);
}

/* ── Animation ── */
.select-menu-enter-active {
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}
.select-menu-leave-active {
  transition: opacity var(--transition-fast), transform var(--transition-fast);
}
.select-menu-enter-from {
  opacity: 0;
  transform: translateY(-4px);
}
.select-menu-leave-to {
  opacity: 0;
  transform: translateY(-4px);
}
</style>
