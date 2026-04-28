<script setup lang="ts">
import { ref } from "vue";
import type { TimePreset } from "../types/traces";

const props = defineProps<{
  presets: TimePreset[];
  activePreset: TimePreset;
}>();

const emit = defineEmits<{
  select: [preset: TimePreset];
}>();

const open = ref(false);

function selectPreset(p: TimePreset) {
  emit("select", p);
  open.value = false;
}

function toggle() {
  open.value = !open.value;
}

function handleClickOutside(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest(".time-filter");
  if (!el) open.value = false;
}

import { onMounted as mount, onUnmounted as unmount } from "vue";
mount(() => document.addEventListener("click", handleClickOutside));
unmount(() => document.removeEventListener("click", handleClickOutside));
</script>

<template>
  <div class="time-filter">
    <button class="trigger" @click="toggle">
      <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
        <rect x="2" y="3" width="12" height="11" rx="1" stroke="currentColor" stroke-width="1.2" />
        <path d="M2 6h12M5 1v3M11 1v3" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" />
      </svg>
      <span>{{ activePreset.label }}</span>
      <svg
        class="chevron"
        :class="{ flipped: open }"
        width="10"
        height="10"
        viewBox="0 0 10 10"
        fill="none"
      >
        <path d="M2 4l3 3 3-3" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
    </button>
    <div v-if="open" class="dropdown">
      <ul class="preset-list">
        <li
          v-for="p in presets"
          :key="p.value"
          class="preset-item"
          :class="{ active: p.value === activePreset.value }"
          @click="selectPreset(p)"
        >
          {{ p.label }}
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.time-filter {
  position: relative;
}

.trigger {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border-radius: 20px;
  background: #fff;
  color: var(--gray-600);
  font-size: 14px;
  font-family: var(--font-sans);
  border: 1px solid var(--gray-200);
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}

.trigger:hover {
  background: var(--blue-50);
  color: var(--blue-500);
  border-color: var(--blue-200);
}

.chevron {
  transition: transform 0.2s;
}

.chevron.flipped {
  transform: rotate(180deg);
}

.dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  width: 220px;
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
  z-index: 50;
  overflow: hidden;
}

.preset-list {
  list-style: none;
  max-height: 360px;
  overflow-y: auto;
}

.preset-item {
  padding: 10px 20px;
  font-size: 15px;
  font-family: var(--font-sans);
  color: var(--gray-900);
  cursor: pointer;
  transition: background 0.1s;
}

.preset-item:hover {
  background: var(--gray-50);
}

.preset-item.active {
  background: var(--blue-50);
  color: var(--blue-600);
  font-weight: 600;
}
</style>
