<script setup lang="ts">
import { ref, reactive, watch, onMounted, onUnmounted, nextTick } from "vue";
import type { LogEntry } from "../types/logs";
import { withGuid, apiUrl } from "../guid";

const props = defineProps<{
  timeRange: { from: string; to: string };
}>();

const PAGE_SIZE = 500;
const MAX_ENTRIES = 500;

let nextId = 0;
interface IdEntry extends LogEntry {
  _id: number;
}

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
    if (state.entries.length > MAX_ENTRIES) {
      state.entries.length = MAX_ENTRIES;
    }
  } else {
    state.buffered.unshift(entry);
    if (state.buffered.length > MAX_ENTRIES) {
      state.buffered.length = MAX_ENTRIES;
      state.overflow = true;
    }
  }
}

function stopTail() {
  if (eventSource) {
    eventSource.close();
    eventSource = null;
  }
}

function startTail() {
  stopTail();

  const newestTs = state.entries[0]?.timestamp;
  const qs = withGuid(new URLSearchParams());
  if (newestTs) {
    qs.set("from", newestTs);
  } else if (props.timeRange.from) {
    qs.set("from", props.timeRange.from);
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
    const qs = withGuid(new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: "0",
    }));
    if (props.timeRange.from) qs.set("from", props.timeRange.from);
    if (props.timeRange.to) qs.set("to", props.timeRange.to);

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
    const qs = withGuid(new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(state.offset),
    }));
    if (props.timeRange.from) qs.set("from", props.timeRange.from);
    if (props.timeRange.to) qs.set("to", props.timeRange.to);

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

  if (atTop && !state.isAtTop) {
    state.isAtTop = true;
    flushBuffer();
  } else if (!atTop && state.isAtTop) {
    state.isAtTop = false;
  }

  if (atBottom && state.hasMore) {
    loadMore();
  }
}

function flushBuffer() {
  if (state.overflow) {
    loadInitialBatch();
    return;
  }
  if (state.buffered.length > 0) {
    const sorted = sortDesc(state.buffered);
    state.entries.unshift(...sorted);
    if (state.entries.length > MAX_ENTRIES) {
      state.entries.length = MAX_ENTRIES;
    }
    state.buffered = [];
    state.overflow = false;
  }
  nextTick(() => {
    if (tableBody.value) tableBody.value.scrollTop = 0;
  });
}

function scrollToTopAndResume() {
  state.isAtTop = true;
  flushBuffer();
}

function sourceBadgeClass(source: string): string {
  if (source === "stdout") return "badge-stdout";
  if (source === "stderr") return "badge-stderr";
  return "badge-otel";
}

function sourceLabel(source: string): string {
  if (source === "stdout") return "stdout";
  if (source === "stderr") return "stderr";
  return "otel";
}

function formatTimestamp(ts: string): string {
  const d = new Date(ts);
  const y = d.getFullYear();
  const mo = (d.getMonth() + 1).toString().padStart(2, "0");
  const day = d.getDate().toString().padStart(2, "0");
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  const ms = d.getMilliseconds().toString().padStart(3, "0");
  return `${y}/${mo}/${day} ${h}:${m}:${s}.${ms}`;
}

function severityClass(sev: string): string {
  if (sev === "error") return "sev-error";
  if (sev === "warn") return "sev-warn";
  return "";
}

watch(() => props.timeRange, () => loadInitialBatch(), { deep: true });
onMounted(() => loadInitialBatch());
onUnmounted(() => stopTail());
</script>

<template>
  <div class="log-table-wrapper">
    <div class="table-header">
      <div class="col col-source">Source</div>
      <div class="col col-process">Process ID</div>
      <div class="col col-entry">Log Entries</div>
      <div class="tail-status">
        <span v-if="state.isAtTop" class="status-live">
          <span class="live-dot" /> Live
        </span>
        <span v-else class="status-paused">Paused</span>
      </div>
    </div>

    <div
      v-if="!state.isAtTop && state.buffered.length > 0"
      class="buffer-banner"
      @click="scrollToTopAndResume"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M8 12V4M5 7l3-3 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      {{ state.buffered.length }} new log{{ state.buffered.length === 1 ? "" : "s" }}
      — click to scroll to top
    </div>

    <div v-if="state.isLoading && state.entries.length === 0" class="empty-state">
      Loading logs...
    </div>
    <div v-else-if="state.entries.length === 0" class="empty-state">
      No log entries found for the selected time range.
    </div>

    <div
      v-else
      ref="tableBody"
      class="table-body"
      @scroll="onScroll"
    >
      <div
        v-for="(entry, i) in state.entries"
        :key="entry._id"
        class="log-row"
        :class="[severityClass(entry.severity), { alt: i % 2 === 1 }]"
      >
        <div class="col col-source">
          <span class="source-badge" :class="sourceBadgeClass(entry.source)">
            {{ sourceLabel(entry.source) }}
          </span>
        </div>
        <div class="col col-process">
          <span class="process-badge">{{ entry.job_key || "—" }}</span>
        </div>
        <div class="col col-entry mono">
          <span class="log-timestamp">{{ formatTimestamp(entry.timestamp) }}</span>
          <span v-if="entry.severity" class="log-severity">{{ entry.severity.toUpperCase() }}</span>
          <span class="log-body" :class="{ 'stderr-text': entry.source === 'stderr' }">{{ entry.body }}</span>
        </div>
      </div>
      <div v-if="state.isLoading" class="loading-more">Loading more...</div>
    </div>
  </div>
</template>

<style scoped>
.log-table-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.table-header {
  display: grid;
  grid-template-columns: 90px 150px minmax(0, 1fr) auto;
  padding: 6px 16px;
  border-bottom: 1px solid var(--gray-200);
  background: var(--gray-50);
  flex-shrink: 0;
  align-items: center;
}

.table-header .col {
  font-family: var(--font-mono);
  font-size: 12px;
  font-weight: 600;
  color: var(--gray-700);
}

.tail-status {
  font-size: 11px;
  font-family: var(--font-sans);
  font-weight: 600;
  display: flex;
  align-items: center;
  justify-content: flex-end;
}

.status-live {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--green-500);
}

.live-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--green-500);
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.status-paused {
  color: var(--orange-500);
}

.buffer-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 16px;
  background: var(--blue-50);
  color: var(--blue-700);
  border-bottom: 1px solid var(--blue-200);
  font-size: 13px;
  font-family: var(--font-sans);
  font-weight: 500;
  cursor: pointer;
  flex-shrink: 0;
  transition: background 0.15s;
}

.buffer-banner:hover {
  background: var(--blue-100);
}

.table-body {
  flex: 1;
  overflow-y: auto;
  background: var(--gray-50);
}

.log-row {
  display: grid;
  grid-template-columns: 90px 150px minmax(0, 1fr);
  padding: 2px 16px;
  align-items: center;
  min-height: 24px;
  transition: background 0.1s;
}

.log-row:hover {
  background: var(--gray-100);
}

.log-row.alt {
  background: #fff;
}

.log-row.alt:hover {
  background: var(--gray-100);
}

.log-row.sev-error {
  background: var(--red-50);
}

.log-row.sev-warn {
  background: var(--orange-50);
}

.mono {
  font-family: var(--font-mono);
}

.source-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.badge-stdout {
  background: var(--green-100);
  color: var(--green-800);
}

.badge-stderr {
  background: var(--red-100);
  color: var(--red-700);
}

.badge-otel {
  background: var(--otel-bg);
  color: var(--otel-text);
}

.process-badge {
  display: inline-block;
  padding: 2px 8px;
  border-radius: 6px;
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--blue-100);
  color: var(--blue-800);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 100%;
  cursor: pointer;
  transition: background 0.15s;
}

.process-badge:hover {
  background: var(--blue-200);
}

.col-entry {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  color: var(--gray-900);
  min-width: 0;
  overflow: hidden;
}

.log-timestamp {
  color: var(--gray-400);
  font-size: 12px;
  white-space: nowrap;
  flex-shrink: 0;
}

.log-severity {
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  color: var(--gray-500);
}

.sev-error .log-severity {
  color: var(--red-500);
}

.sev-warn .log-severity {
  color: var(--orange-500);
}

.log-body {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
}

.stderr-text {
  color: var(--red-600);
}

.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: var(--gray-500);
  font-size: 14px;
}

.loading-more {
  text-align: center;
  padding: 12px;
  color: var(--gray-400);
  font-size: 13px;
}
</style>
