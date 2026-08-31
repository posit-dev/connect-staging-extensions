<script setup lang="ts">
import { ref, reactive, onMounted, onUnmounted, nextTick } from "vue";
import type { LogEntry } from "../types/logs";
import type { TimePreset } from "../types/traces";
import { withGuid, apiUrl } from "../guid";

const TIME_PRESETS: TimePreset[] = [
  { label: "Last 5 minutes", value: 5 * 60 * 1000 },
  { label: "Last 15 minutes", value: 15 * 60 * 1000 },
  { label: "Last 30 minutes", value: 30 * 60 * 1000 },
  { label: "Last hour", value: 60 * 60 * 1000 },
  { label: "Last 6 hours", value: 6 * 60 * 60 * 1000 },
  { label: "Last day", value: 24 * 60 * 60 * 1000 },
];

const activePreset = ref<TimePreset>(TIME_PRESETS[0]);
const timeDropdownOpen = ref(false);

const PAGE_SIZE = 500;
const MAX_ENTRIES = 500;

let nextId = 0;
interface IdEntry extends LogEntry { _id: number; }

const state = reactive({
  entries: [] as IdEntry[],
  buffered: [] as IdEntry[],
  isAtTop: true,
  hasMore: false,
  isLoading: false,
  offset: 0,
  overflow: false,
});

const tableBody = ref<HTMLElement | null>(null);
let eventSource: EventSource | null = null;

function stamp(e: LogEntry): IdEntry {
  return { ...e, _id: nextId++ };
}

function sortDesc(entries: IdEntry[]): IdEntry[] {
  return [...entries].sort(
    (a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime()
  );
}

function injectEntry(entry: IdEntry) {
  if (state.isAtTop) {
    state.entries.unshift(entry);
    if (state.entries.length > MAX_ENTRIES) state.entries.length = MAX_ENTRIES;
  } else {
    state.buffered.unshift(entry);
    if (state.buffered.length > MAX_ENTRIES) {
      state.buffered.length = MAX_ENTRIES;
      state.overflow = true;
    }
  }
}

function stopTail() {
  if (eventSource) { eventSource.close(); eventSource = null; }
}

function freshTimeRange() {
  const now = new Date();
  const from = new Date(now.getTime() - activePreset.value.value);
  return { from: from.toISOString(), to: now.toISOString() };
}

function startTail() {
  stopTail();
  const newestTs = state.entries[0]?.timestamp;
  const qs = withGuid(new URLSearchParams());
  if (newestTs) qs.set("from", newestTs);
  else {
    const range = freshTimeRange();
    qs.set("from", range.from);
  }

  eventSource = new EventSource(apiUrl(`/api/logs/tail?${qs}`));
  eventSource.addEventListener("entry", (evt) => {
    try {
      const raw = JSON.parse((evt as MessageEvent).data);
      const entry: LogEntry = {
        timestamp: raw.timestamp,
        severity: raw.severity ?? "",
        body: raw.body ?? "",
        job_key: raw.jobKey ?? "",
        source: raw.ioStream || "otel",
        hostname: raw.hostname ?? "",
        io_stream: raw.ioStream ?? "",
        process_id: raw.processId ?? 0,
        trace_id: "",
        span_id: "",
      };
      injectEntry(stamp(entry));
    } catch {}
  });
}

async function loadInitialBatch() {
  stopTail();
  state.isLoading = true;
  state.entries = [];
  state.buffered = [];
  state.overflow = false;
  state.offset = 0;

  try {
    const range = freshTimeRange();
    const qs = withGuid(new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: "0",
      from: range.from,
      to: range.to,
    }));
    const resp = await fetch(apiUrl(`/api/logs?${qs}`));
    const data = await resp.json();
    const raw: LogEntry[] = data.entries ?? [];
    state.entries = sortDesc(raw.map(stamp));
    state.offset = raw.length;
    state.hasMore = raw.length >= PAGE_SIZE;
  } catch (e) {
    console.error("Failed to fetch logs:", e);
    state.entries = [];
  } finally {
    state.isLoading = false;
    startTail();
  }
}

async function loadMore() {
  if (state.isLoading || !state.hasMore) return;
  state.isLoading = true;
  try {
    const range = freshTimeRange();
    const qs = withGuid(new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(state.offset),
      from: range.from,
      to: range.to,
    }));
    const resp = await fetch(apiUrl(`/api/logs?${qs}`));
    const data = await resp.json();
    const raw: LogEntry[] = data.entries ?? [];
    state.entries.push(...sortDesc(raw.map(stamp)));
    state.offset += raw.length;
    state.hasMore = raw.length >= PAGE_SIZE;
  } catch (e) {
    console.error("Failed to load more logs:", e);
  } finally {
    state.isLoading = false;
  }
}

function onScroll() {
  if (!tableBody.value) return;
  const el = tableBody.value;
  const atTop = el.scrollTop < 40;
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 100;
  if (atTop && !state.isAtTop) { state.isAtTop = true; flushBuffer(); }
  else if (!atTop && state.isAtTop) { state.isAtTop = false; }
  if (atBottom && state.hasMore) loadMore();
}

function flushBuffer() {
  if (state.overflow) { loadInitialBatch(); return; }
  if (state.buffered.length > 0) {
    const sorted = sortDesc(state.buffered);
    state.entries.unshift(...sorted);
    if (state.entries.length > MAX_ENTRIES) state.entries.length = MAX_ENTRIES;
    state.buffered = [];
    state.overflow = false;
  }
  nextTick(() => { if (tableBody.value) tableBody.value.scrollTop = 0; });
}

function scrollToTopAndResume() {
  state.isAtTop = true;
  flushBuffer();
}

function selectPreset(preset: TimePreset) {
  activePreset.value = preset;
  timeDropdownOpen.value = false;
  loadInitialBatch();
}

function sourceBadgeClass(source: string): string {
  if (source === "stdout") return "src-stdout";
  if (source === "stderr") return "src-stderr";
  return "src-otel";
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  const ms = d.getMilliseconds().toString().padStart(3, "0");
  return `${h}:${m}:${s}.${ms}`;
}

function severityClass(sev: string): string {
  if (sev === "error") return "sev-error";
  if (sev === "warn") return "sev-warn";
  return "";
}

onMounted(() => loadInitialBatch());
onUnmounted(() => stopTail());
</script>

<template>
  <div class="logs-view">
    <div class="top-bar">
      <div class="top-left">
        <span class="view-label">Logs</span>
        <span v-if="state.isAtTop" class="live-badge">
          <span class="live-dot" /> Live
        </span>
        <span v-else class="paused-badge">Paused</span>
      </div>
      <div class="top-right">
        <button class="refresh-btn" @click="loadInitialBatch" title="Refresh">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="M2.5 8a5.5 5.5 0 0 1 9.9-3.3M13.5 8a5.5 5.5 0 0 1-9.9 3.3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
            <path d="M12 1.5v3.5h-3.5M4 11h3.5v3.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
          </svg>
        </button>
        <div class="time-selector" @click.stop>
          <button class="time-btn" @click="timeDropdownOpen = !timeDropdownOpen">
            {{ activePreset.label }}
            <svg width="10" height="10" viewBox="0 0 10 10"><path d="M2 3.5l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.2" /></svg>
          </button>
          <div v-if="timeDropdownOpen" class="time-dropdown">
            <button
              v-for="p in TIME_PRESETS"
              :key="p.label"
              :class="{ active: p.label === activePreset.label }"
              @click="selectPreset(p)"
            >{{ p.label }}</button>
          </div>
        </div>
      </div>
    </div>

    <div
      v-if="!state.isAtTop && state.buffered.length > 0"
      class="buffer-banner"
      @click="scrollToTopAndResume"
    >
      {{ state.buffered.length }} new log{{ state.buffered.length === 1 ? "" : "s" }} -- click to scroll to top
    </div>

    <div v-if="state.isLoading && state.entries.length === 0" class="empty-state">Loading logs...</div>
    <div v-else-if="state.entries.length === 0" class="empty-state">No log entries found.</div>

    <div v-else ref="tableBody" class="log-body" @scroll="onScroll">
      <div
        v-for="entry in state.entries"
        :key="entry._id"
        class="log-row"
        :class="severityClass(entry.severity)"
      >
        <span class="log-source" :class="sourceBadgeClass(entry.source)">{{ entry.source }}</span>
        <span class="log-pid mono">{{ entry.job_key || "--" }}</span>
        <span class="log-time mono">{{ formatTimestamp(entry.timestamp) }}</span>
        <span v-if="entry.severity" class="log-severity mono" :class="severityClass(entry.severity)">{{ entry.severity.toUpperCase() }}</span>
        <span class="log-text mono">{{ entry.body }}</span>
      </div>
      <div v-if="state.isLoading" class="loading-more">Loading more...</div>
    </div>
  </div>
</template>

<style scoped>
.logs-view {
  display: flex;
  flex-direction: column;
  flex: 1;
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

.top-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

.view-label {
  font-size: 14px;
  font-weight: 600;
}

.live-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-green);
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-green);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.paused-badge {
  font-size: 11px;
  font-weight: 600;
  color: var(--accent-orange);
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
}

.refresh-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.time-selector { position: relative; }

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
}

.time-btn:hover { background: var(--bg-hover); }

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

.buffer-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  background: var(--accent-blue-dim);
  color: var(--accent-blue);
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
}

.buffer-banner:hover {
  background: rgba(74, 144, 217, 0.25);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: var(--text-muted);
  font-size: 14px;
  flex: 1;
}

.log-body {
  flex: 1;
  overflow-y: auto;
}

.log-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 3px 16px;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
  min-height: 24px;
}

.log-row:hover {
  background: var(--bg-hover);
}

.log-row.sev-error {
  background: var(--accent-red-dim);
}

.log-row.sev-warn {
  background: var(--accent-orange-dim);
}

.log-source {
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
  flex-shrink: 0;
  font-family: var(--font-mono);
}

.src-stdout { background: var(--accent-green-dim); color: var(--accent-green); }
.src-stderr { background: var(--accent-red-dim); color: var(--accent-red); }
.src-otel { background: var(--accent-blue-dim); color: var(--accent-blue); }

.log-pid {
  color: var(--text-muted);
  font-size: 11px;
  flex-shrink: 0;
  min-width: 80px;
}

.log-time {
  color: var(--text-muted);
  font-size: 11px;
  flex-shrink: 0;
}

.log-severity {
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
  color: var(--text-muted);
}

.log-severity.sev-error { color: var(--accent-red); }
.log-severity.sev-warn { color: var(--accent-orange); }

.log-text {
  color: var(--text-secondary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.mono { font-family: var(--font-mono); }

.loading-more {
  text-align: center;
  padding: 12px;
  color: var(--text-muted);
  font-size: 13px;
}
</style>
