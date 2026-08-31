<script setup lang="ts">
import { useRoute } from "vue-router";

const route = useRoute();

function isActive(path: string): boolean {
  return route.path.startsWith(path);
}
</script>

<template>
  <nav class="sidebar">
    <div class="logo">
      <svg width="28" height="28" viewBox="0 0 28 28" fill="none">
        <rect width="28" height="28" rx="6" fill="var(--blue-500)" />
        <text x="7" y="20" font-size="16" font-weight="700" fill="#fff" font-family="Open Sans, sans-serif">S</text>
      </svg>
    </div>
    <div class="nav-items">
      <router-link
        to="/traces"
        class="nav-item"
        :class="{ active: isActive('/traces') }"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M3 12h4l3-9 4 18 3-9h4" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
        <span>Traces</span>
      </router-link>
      <router-link
        to="/logs"
        class="nav-item"
        :class="{ active: isActive('/logs') }"
      >
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
          <path d="M4 6h16M4 10h16M4 14h10M4 18h12" stroke-linecap="round" />
        </svg>
        <span>Logs</span>
      </router-link>
    </div>
  </nav>
</template>

<style scoped>
.sidebar {
  width: 60px;
  background: #fff;
  border-right: 1px solid var(--gray-200);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 12px 0;
  flex-shrink: 0;
  gap: 8px;
}

.logo {
  margin-bottom: 16px;
}

.nav-items {
  display: flex;
  flex-direction: column;
  gap: 2px;
  width: 100%;
}

.nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 8px 4px;
  color: var(--gray-400);
  text-decoration: none;
  font-size: 9px;
  font-weight: 500;
  transition: all 0.15s;
  border-left: 3px solid transparent;
}

.nav-item:hover {
  color: var(--blue-500);
  background: var(--blue-50);
  text-decoration: none;
}

.nav-item.active {
  color: var(--blue-500);
  border-left-color: var(--blue-500);
  background: var(--blue-50);
}
</style>
