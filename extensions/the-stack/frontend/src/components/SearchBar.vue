<script setup lang="ts">
defineProps<{ modelValue: string }>();
defineEmits<{ "update:modelValue": [value: string] }>();
</script>

<template>
  <div class="search-wrapper">
    <svg class="search-icon" width="16" height="16" viewBox="0 0 16 16" fill="none">
      <circle cx="7" cy="7" r="5" stroke="currentColor" stroke-width="1.5" />
      <path d="M11 11l3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
    </svg>
    <input
      type="text"
      class="search-input"
      placeholder="Search & filter with SQL..."
      :value="modelValue"
      @input="$emit('update:modelValue', ($event.target as HTMLInputElement).value)"
    />
  </div>
</template>

<style scoped>
.search-wrapper {
  position: relative;
  flex: 1;
  max-width: 480px;
}

.search-icon {
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  color: var(--gray-400);
  pointer-events: none;
}

.search-input {
  width: 100%;
  height: 32px;
  padding: 4px 8px 4px 34px;
  border: 1px solid var(--gray-300);
  border-radius: 4px;
  font-size: 14px;
  font-family: var(--font-mono);
  color: var(--gray-900);
  background: #fff;
  outline: none;
  transition: border-color 0.15s;
}

.search-input:focus {
  border-color: var(--blue-500);
  box-shadow: 0 0 0 1px var(--blue-500);
}

.search-input::placeholder {
  color: var(--gray-400);
}
</style>
