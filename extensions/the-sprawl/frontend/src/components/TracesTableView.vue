<script setup lang="ts">
import { ref, inject, computed, onMounted, watch } from "vue";
import type { Ref } from "vue";
import { useRouter } from "vue-router";
import type { TraceGroup, TimePreset } from "../types/traces";
import { fetchTraceSpans, fetchLogs, buildTraceGroups } from "../api/client";
import type { Span } from "../types/traces";

const router = useRouter();
const setupRequired = inject<Ref<boolean>>("setupRequired")!;

const TIME_PRESETS: TimePreset[] = [
  { label: "Last 5 minutes", value: 5 * 60 * 1000 },
  { label: "Last 15 minutes", value: 15 * 60 * 1000 },
  { label: "Last 30 minutes", value: 30 * 60 * 1000 },
  { label: "Last hour", value: 60 * 60 * 1000 },
  { label: "Last 6 hours", value: 6 * 60 * 60 * 1000 },
  { label: "Last 12 hours", value: 12 * 60 * 60 * 1000 },
  { label: "Last day", value: 24 * 60 * 60 * 1000 },
  { label: "Last 7 days", value: 7 * 24 * 60 * 60 * 1000 },
];

const activePreset = ref<TimePreset | null>(TIME_PRESETS[0]);
const groups = ref<TraceGroup[]>([]);
const totalSpans = ref(0);
const loading = ref(false);
const page = ref(1);
const perPage = ref(20);
const timeDropdownOpen = ref(false);

const customFromDate = ref("");
const customFromTime = ref("00:00");
const customToDate = ref("");
const customToTime = ref("23:59");
const customRangeOpen = ref(false);

const statusFilter = ref<"all" | "error" | "warn" | "none">("all");
const serviceFilter = ref("");
const durationMin = ref<number | null>(null);
const durationMax = ref<number | null>(null);

const traceLogSeverities = ref(new Map<string, Set<string>>());

function traceHasError(traceId: string, spans: Span[]): boolean {
  if (spans.some((s) => s.statusCode === 2)) return true;
  const sevs = traceLogSeverities.value.get(traceId);
  return sevs?.has("error") ?? false;
}

function traceHasWarn(traceId: string): boolean {
  const sevs = traceLogSeverities.value.get(traceId);
  return sevs?.has("warn") ?? false;
}

const filteredGroups = computed(() => {
  let g = groups.value;
  if (statusFilter.value === "error") {
    g = g.filter((t) => traceHasError(t.traceId, t.spans));
  } else if (statusFilter.value === "warn") {
    g = g.filter((t) => traceHasWarn(t.traceId) && !traceHasError(t.traceId, t.spans));
  } else if (statusFilter.value === "none") {
    g = g.filter((t) => !traceHasError(t.traceId, t.spans) && !traceHasWarn(t.traceId));
  }
  if (serviceFilter.value) {
    const s = serviceFilter.value.toLowerCase();
    g = g.filter((t) => t.rootSpan.serviceName.toLowerCase().includes(s));
  }
  if (typeof durationMin.value === "number" && !isNaN(durationMin.value)) {
    g = g.filter((t) => t.rootSpan.duration >= durationMin.value!);
  }
  if (typeof durationMax.value === "number" && !isNaN(durationMax.value)) {
    g = g.filter((t) => t.rootSpan.duration <= durationMax.value!);
  }
  return g;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredGroups.value.length / perPage.value)));
const paginatedGroups = computed(() => {
  const start = (page.value - 1) * perPage.value;
  return filteredGroups.value.slice(start, start + perPage.value);
});

const uniqueServices = computed(() => {
  const s = new Set<string>();
  for (const g of groups.value) {
    if (g.rootSpan.serviceName) s.add(g.rootSpan.serviceName);
  }
  return [...s].sort();
});

function freshTimeRange() {
  if (customFromDate.value && customToDate.value) {
    return {
      from: new Date(`${customFromDate.value}T${customFromTime.value}`).toISOString(),
      to: new Date(`${customToDate.value}T${customToTime.value}`).toISOString(),
    };
  }
  const now = new Date();
  const from = new Date(now.getTime() - (activePreset.value?.value ?? 5 * 60 * 1000));
  return { from: from.toISOString(), to: now.toISOString() };
}

async function loadTraces() {
  loading.value = true;
  try {
    const range = freshTimeRange();
    const [traceResult, logResult] = await Promise.all([
      fetchTraceSpans({ from: range.from, to: range.to }),
      fetchLogs({ from: range.from, to: range.to, limit: 1000 }),
    ]);
    totalSpans.value = traceResult.total;
    const fresh = traceResult.spans.map((s) => ({ ...s, children: [] as Span[], depth: 0 }));
    groups.value = buildTraceGroups(fresh);

    const sevMap = new Map<string, Set<string>>();
    for (const log of logResult.entries) {
      if (log.trace_id && log.severity) {
        let set = sevMap.get(log.trace_id);
        if (!set) { set = new Set(); sevMap.set(log.trace_id, set); }
        set.add(log.severity);
      }
    }
    traceLogSeverities.value = sevMap;

    page.value = 1;
  } catch (e: any) {
    if (e?.message === "SETUP_REQUIRED") {
      setupRequired.value = true;
      return;
    }
    console.error("Failed to fetch traces:", e);
  } finally {
    loading.value = false;
  }
}

function selectPreset(preset: TimePreset) {
  activePreset.value = preset;
  customFromDate.value = "";
  customFromTime.value = "00:00";
  customToDate.value = "";
  customToTime.value = "23:59";
  timeDropdownOpen.value = false;
  loadTraces();
}

function applyCustomRange() {
  if (customFromDate.value && customToDate.value) {
    activePreset.value = null;
    customRangeOpen.value = false;
    loadTraces();
  }
}

function goToTrace(traceId: string) {
  router.push({ name: "trace-detail", params: { traceId } });
}

function formatDuration(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(2)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatTime(ms: number): string {
  const d = new Date(ms);
  const day = d.getDate().toString().padStart(2, "0");
  const month = d.toLocaleString("en", { month: "short" });
  const year = d.getFullYear();
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  return `${day} ${month} ${year}, ${h}:${m}:${s}`;
}

function clearFilters() {
  statusFilter.value = "all";
  serviceFilter.value = "";
  durationMin.value = null;
  durationMax.value = null;
}

watch(() => [statusFilter.value, serviceFilter.value, durationMin.value, durationMax.value], () => {
  page.value = 1;
});

onMounted(() => loadTraces());
</script>

<template>
  <div class="traces-view">
    <div class="filter-sidebar">
      <div class="filter-header">
        <span>Filters</span>
        <button class="clear-btn" @click="clearFilters">Clear All</button>
      </div>

      <details class="filter-section" open>
        <summary>Duration</summary>
        <div class="filter-body duration-inputs">
          <label>
            <span>MIN</span>
            <input type="number" v-model.number="durationMin" placeholder="0" />
            <span class="unit">ms</span>
          </label>
          <label>
            <span>MAX</span>
            <input type="number" v-model.number="durationMax" placeholder="&infin;" />
            <span class="unit">ms</span>
          </label>
        </div>
      </details>

      <details class="filter-section">
        <summary>Status</summary>
        <div class="filter-body">
          <label class="radio-label">
            <input type="radio" value="all" v-model="statusFilter" /> All
          </label>
          <label class="radio-label">
            <input type="radio" value="error" v-model="statusFilter" /> Error
          </label>
          <label class="radio-label">
            <input type="radio" value="warn" v-model="statusFilter" /> Warning
          </label>
          <label class="radio-label">
            <input type="radio" value="none" v-model="statusFilter" /> Clean
          </label>
        </div>
      </details>

      <details class="filter-section">
        <summary>Service Name</summary>
        <div class="filter-body">
          <input
            type="text"
            class="filter-input"
            v-model="serviceFilter"
            placeholder="Filter services..."
          />
          <div class="filter-values">
            <div v-for="s in uniqueServices" :key="s" class="filter-value" @click="serviceFilter = s">
              {{ s }}
            </div>
            <div v-if="uniqueServices.length === 0" class="filter-empty">No values found</div>
          </div>
        </div>
      </details>
    </div>

    <div class="traces-main">
      <div class="top-bar">
        <div class="view-tabs">
          <span class="view-tab active">Trace View</span>
        </div>
        <div class="top-right">
          <button class="refresh-btn" @click="loadTraces" title="Refresh">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="M2.5 8a5.5 5.5 0 0 1 9.9-3.3M13.5 8a5.5 5.5 0 0 1-9.9 3.3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              <path d="M12 1.5v3.5h-3.5M4 11h3.5v3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </button>
          <div class="time-selector" @click.stop>
            <button class="time-btn" @click="timeDropdownOpen = !timeDropdownOpen">
              {{ activePreset?.label ?? "Custom" }}
              <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.2" /></svg>
            </button>
            <div v-if="timeDropdownOpen" class="time-dropdown">
              <button
                v-for="p in TIME_PRESETS"
                :key="p.label"
                :class="{ active: activePreset?.label === p.label }"
                @click="selectPreset(p)"
              >{{ p.label }}</button>
            </div>
          </div>
          <div class="custom-range-selector" @click.stop>
            <button class="time-btn" @click="customRangeOpen = !customRangeOpen">
              Custom range
            </button>
            <div v-if="customRangeOpen" class="custom-range-dropdown">
              <div class="date-row">
                <span class="date-row-label">From</span>
                <input type="date" class="date-picker" v-model="customFromDate" />
                <input type="time" class="time-picker" v-model="customFromTime" />
              </div>
              <div class="date-row">
                <span class="date-row-label">To</span>
                <input type="date" class="date-picker" v-model="customToDate" />
                <input type="time" class="time-picker" v-model="customToTime" />
              </div>
              <button class="apply-btn" :disabled="!customFromDate || !customToDate" @click="applyCustomRange">Apply</button>
            </div>
          </div>
        </div>
      </div>

      <div class="table-info">
        Root Spans only. Showing {{ (page - 1) * perPage + 1 }}–{{ Math.min(page * perPage, filteredGroups.length) }} of {{ filteredGroups.length }} traces ({{ totalSpans }} total spans).
      </div>

      <div v-if="loading" class="loading-state">Loading traces...</div>
      <div v-else-if="filteredGroups.length === 0" class="empty-state">No traces found for the selected time range.</div>

      <div v-else class="table-container">
        <table class="traces-table">
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Root Operation Name</th>
              <th>Root Duration</th>
              <th>No of Spans</th>
              <th>TraceID</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="g in paginatedGroups"
              :key="g.traceId"
              :class="{ 'row-error': traceHasError(g.traceId, g.spans), 'row-warn': !traceHasError(g.traceId, g.spans) && traceHasWarn(g.traceId) }"
              @click="goToTrace(g.traceId)"
            >
              <td class="mono">{{ formatTime(g.rootSpan.startTime) }}</td>
              <td class="mono">{{ g.rootSpan.name }}</td>
              <td class="mono">{{ formatDuration(g.rootSpan.duration) }}</td>
              <td>{{ g.spans.length }}</td>
              <td class="mono trace-id">{{ g.traceId }}</td>
            </tr>
          </tbody>
        </table>

        <div v-if="!loading && filteredGroups.length > 0" class="pagination">
          <button :disabled="page <= 1" @click="page--">Previous</button>
          <span class="page-info">{{ page }} / {{ totalPages }}</span>
          <button :disabled="page >= totalPages" @click="page++">Next</button>
          <select v-model.number="perPage" @change="page = 1">
            <option :value="20">20 / page</option>
            <option :value="50">50 / page</option>
            <option :value="100">100 / page</option>
          </select>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.traces-view {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.filter-sidebar {
  width: 200px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-secondary);
  overflow-y: auto;
  padding: 12px 0;
}

.filter-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 12px 12px;
  font-size: 13px;
  font-weight: 600;
  border-bottom: 1px solid var(--border);
}

.clear-btn {
  font-size: 11px;
  background: none;
  border: none;
  color: var(--accent-blue);
  cursor: pointer;
}

.filter-section {
  border-bottom: 1px solid var(--border);
}

.filter-section summary {
  padding: 8px 12px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-secondary);
  cursor: pointer;
  user-select: none;
}

.filter-section summary:hover {
  color: var(--text-primary);
}

.filter-body {
  padding: 0 12px 8px;
}

.duration-inputs label {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 11px;
  color: var(--text-muted);
}

.duration-inputs input {
  width: 60px;
  padding: 3px 6px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 11px;
  font-family: var(--font-mono);
}

.duration-inputs .unit {
  color: var(--text-muted);
}

.radio-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text-secondary);
  padding: 2px 0;
  cursor: pointer;
}

.filter-input {
  width: 100%;
  padding: 4px 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 12px;
  margin-bottom: 6px;
}

.filter-values {
  max-height: 120px;
  overflow-y: auto;
}

.filter-value {
  padding: 3px 4px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
  cursor: pointer;
  border-radius: 3px;
}

.filter-value:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.filter-empty {
  font-size: 11px;
  color: var(--text-muted);
  padding: 4px 0;
}

.traces-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.top-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.view-tabs {
  display: flex;
  gap: 0;
}

.view-tab {
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 4px;
  color: var(--text-muted);
}

.view-tab.active {
  background: var(--blue-100);
  color: var(--blue-600);
  font-weight: 600;
}

.top-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
  transition: all 0.15s;
}

.refresh-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.custom-range-selector {
  position: relative;
}

.custom-range-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
  z-index: 100;
  display: flex;
  flex-direction: column;
  gap: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.date-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.date-row-label {
  font-size: 12px;
  color: var(--text-secondary);
  min-width: 34px;
}

.date-picker,
.time-picker {
  padding: 5px 8px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 12px;
  font-family: var(--font-mono);
}

.date-picker:focus,
.time-picker:focus {
  outline: none;
  border-color: var(--accent-blue);
}

.apply-btn {
  padding: 6px 12px;
  background: var(--accent-blue);
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
}

.apply-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.apply-btn:disabled {
  opacity: 0.4;
  cursor: default;
}

.time-selector {
  position: relative;
}

.time-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-primary);
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}

.time-btn:hover {
  background: var(--bg-hover);
}

.time-dropdown {
  position: absolute;
  top: 100%;
  right: 0;
  margin-top: 4px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px;
  z-index: 100;
  min-width: 160px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

.time-dropdown button {
  display: block;
  width: 100%;
  text-align: left;
  padding: 6px 10px;
  background: none;
  border: none;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
  border-radius: 4px;
}

.time-dropdown button:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.time-dropdown button.active {
  background: var(--accent-blue-dim);
  color: var(--accent-blue);
}

.table-info {
  padding: 8px 16px;
  font-size: 11px;
  color: var(--text-muted);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: var(--text-muted);
  font-size: 14px;
  flex: 1;
}

.table-container {
  flex: 1;
  overflow: auto;
}

.traces-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.traces-table th {
  text-align: left;
  padding: 8px 16px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  background: var(--bg-secondary);
  position: sticky;
  top: 0;
  border-bottom: 1px solid var(--border);
}

.traces-table td {
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
}

.traces-table tbody tr {
  cursor: pointer;
  transition: background 0.1s;
}

.traces-table tbody tr:hover {
  background: var(--bg-hover);
}

.traces-table tbody tr.row-error {
  background: var(--accent-red-dim);
}

.traces-table tbody tr.row-warn {
  background: var(--accent-warn-dim);
}

.traces-table .mono {
  font-family: var(--font-mono);
  font-size: 12px;
}

.traces-table .trace-id {
  color: var(--accent-blue);
  font-size: 11px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
}

.pagination button {
  padding: 4px 12px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 12px;
  cursor: pointer;
}

.pagination button:hover:not(:disabled) {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.pagination button:disabled {
  opacity: 0.3;
  cursor: default;
}

.page-info {
  font-size: 12px;
  color: var(--text-muted);
}

.pagination select {
  padding: 4px 8px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text-secondary);
  font-size: 12px;
}
</style>
