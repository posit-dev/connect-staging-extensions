<script setup lang="ts">
import { ref, provide, onMounted } from "vue";
import AppSidebar from "./components/AppSidebar.vue";
import { contentGuid, apiUrl } from "./guid";

const contentTitle = ref("");
const setupRequired = ref(false);
provide("setupRequired", setupRequired);

async function loadContentTitle() {
  if (!contentGuid) return;
  try {
    const resp = await fetch(apiUrl(`/api/content/${contentGuid}`));
    const data = await resp.json();
    contentTitle.value = data.title || data.name || "";
  } catch {
    contentTitle.value = "";
  }
}

onMounted(() => {
  loadContentTitle();
});
</script>

<template>
  <div v-if="!contentGuid" class="missing-guid">
    <p>Content GUID is required</p>
    <p class="missing-guid-hint">Add <code>?guid=&lt;content-guid&gt;</code> to the URL.</p>
  </div>
  <div v-else-if="setupRequired" class="missing-guid">
    <p>Before you are able to use this app, you need to add a Connect Visitor API Key integration in the access panel.</p>
  </div>
  <div v-else class="app-layout">
    <AppSidebar />
    <main class="main-area">
      <header v-if="contentTitle" class="content-header">
        <h1 class="content-title">{{ contentTitle }}</h1>
      </header>
      <router-view />
    </main>
  </div>
</template>

<style scoped>
.missing-guid {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  color: var(--text-secondary);
  font-family: var(--font-sans);
  font-size: 16px;
  gap: 8px;
}

.missing-guid-hint {
  font-size: 13px;
  color: var(--text-muted);
}

.missing-guid code {
  background: var(--bg-secondary);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.app-layout {
  display: flex;
  height: 100vh;
  overflow: hidden;
}

.main-area {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.content-header {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-primary);
  flex-shrink: 0;
}

.content-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}
</style>
