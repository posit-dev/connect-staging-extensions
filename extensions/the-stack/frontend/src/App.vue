<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from "vue";
import type { TraceGroup, Span, TimePreset } from "./types/traces";
import { fetchTraceSpans, fetchLogs, buildTraceGroups } from "./api/client";
import TimelineHistogram from "./components/TimelineHistogram.vue";
import TraceTable from "./components/TraceTable.vue";
import SpanDetail from "./components/SpanDetail.vue";
import TimeFilter from "./components/TimeFilter.vue";
import LogTable from "./components/LogTable.vue";
import { contentGuid, apiUrl } from "./guid";

type ViewMode = "traces" | "logs";

const TIME_PRESETS: TimePreset[] = [
  { label: "Last 5 minutes", value: 5 * 60 * 1000 },
  { label: "Last 15 minutes", value: 15 * 60 * 1000 },
  { label: "Last 30 minutes", value: 30 * 60 * 1000 },
  { label: "Last hour", value: 60 * 60 * 1000 },
  { label: "Last 6 hours", value: 6 * 60 * 60 * 1000 },
  { label: "Last 12 hours", value: 12 * 60 * 60 * 1000 },
  { label: "Last day", value: 24 * 60 * 60 * 1000 },
  { label: "Last 2 days", value: 2 * 24 * 60 * 60 * 1000 },
  { label: "Last 7 days", value: 7 * 24 * 60 * 60 * 1000 },
  { label: "Last 14 days", value: 14 * 24 * 60 * 60 * 1000 },
  { label: "Last 30 days", value: 30 * 24 * 60 * 60 * 1000 },
];

const TRACE_PAGE = 1000;

const setupRequired = ref(false);
const viewMode = ref<ViewMode>("traces");
const contentTitle = ref("");
const traceGroups = ref<TraceGroup[]>([]);
const bufferedTraceGroups = ref<TraceGroup[]>([]);
const totalTraces = ref(0);
const selectedSpan = ref<Span | null>(null);
const expandedSpans = ref(new Set<string>());
const activePreset = ref<TimePreset>(TIME_PRESETS[0]);
const customRange = ref<{ from: string; to: string } | null>(null);
const loading = ref(false);
const loadingMore = ref(false);
const hasMoreTraces = ref(false);
const liveMode = ref(true);
const tracesAtTop = ref(true);
const customFromDate = ref("");
const customFromTime = ref("00:00");
const customToDate = ref("");
const customToTime = ref("23:59");
const customRangeOpen = ref(false);
let pollTimer: ReturnType<typeof setInterval> | null = null;

let allSpans: Span[] = [];
let spanIndex = new Set<string>();
let traceOffset = 0;

const traceWarnMap = ref(new Set<string>());

function makeTimeRange() {
  const now = new Date();
  const from = new Date(now.getTime() - TIME_PRESETS[0].value);
  return { from: from.toISOString(), to: now.toISOString() };
}

const timeRange = ref(makeTimeRange());

function refreshTimeRange() {
  if (customRange.value) {
    timeRange.value = { from: customRange.value.from, to: customRange.value.to };
  } else {
    const now = new Date();
    const from = new Date(now.getTime() - activePreset.value.value);
    timeRange.value = { from: from.toISOString(), to: now.toISOString() };
  }
}

function rebuildGroups(): TraceGroup[] {
  const fresh = allSpans.map((s) => ({ ...s, children: [] as Span[], depth: 0 }));
  return buildTraceGroups(fresh);
}

async function loadTraces() {
  loading.value = true;
  try {
    allSpans = [];
    spanIndex = new Set<string>();
    traceOffset = 0;

    const { spans, total } = await fetchTraceSpans({
      from: timeRange.value.from,
      to: timeRange.value.to,
      limit: TRACE_PAGE,
      offset: 0,
    });
    totalTraces.value = total;
    for (const s of spans) {
      if (!spanIndex.has(s.spanId)) {
        allSpans.push(s);
        spanIndex.add(s.spanId);
      }
    }
    traceOffset = spans.length;
    hasMoreTraces.value = traceOffset < total;

    const groups = rebuildGroups();
    traceGroups.value = groups;
    bufferedTraceGroups.value = [];

    fetchLogs({ from: timeRange.value.from, to: timeRange.value.to, limit: 1000 }).then(({ entries }) => {
      const warnSpans = new Set<string>();
      for (const log of entries) {
        if (log.span_id && log.severity === "warn") warnSpans.add(log.span_id);
      }
      traceWarnMap.value = warnSpans;
    }).catch(() => {});
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

async function pollTraces() {
  if (customRange.value) return;
  refreshTimeRange();
  try {
    const { spans, total } = await fetchTraceSpans({
      from: timeRange.value.from,
      to: timeRange.value.to,
      limit: TRACE_PAGE,
    });
    totalTraces.value = total;

    let added = 0;
    for (const s of spans) {
      if (!spanIndex.has(s.spanId)) {
        allSpans.push(s);
        spanIndex.add(s.spanId);
        added++;
      }
    }

    if (added > 0) {
      const groups = rebuildGroups();
      if (tracesAtTop.value) {
        traceGroups.value = groups;
      } else {
        bufferedTraceGroups.value = groups;
      }
    }
  } catch (e) {
    console.error("Failed to poll traces:", e);
  }
}

async function loadMoreTraces() {
  if (loadingMore.value || !hasMoreTraces.value) return;
  loadingMore.value = true;
  try {
    const { spans, total } = await fetchTraceSpans({
      from: timeRange.value.from,
      to: timeRange.value.to,
      limit: TRACE_PAGE,
      offset: traceOffset,
    });
    totalTraces.value = total;

    for (const s of spans) {
      if (!spanIndex.has(s.spanId)) {
        allSpans.push(s);
        spanIndex.add(s.spanId);
      }
    }
    traceOffset += spans.length;
    hasMoreTraces.value = traceOffset < total;

    traceGroups.value = rebuildGroups();
  } catch (e) {
    console.error("Failed to load more traces:", e);
  } finally {
    loadingMore.value = false;
  }
}

function flushTraceBuffer() {
  if (bufferedTraceGroups.value.length > 0) {
    traceGroups.value = bufferedTraceGroups.value;
    bufferedTraceGroups.value = [];
  }
}

function onTracesScrollState(atTop: boolean) {
  tracesAtTop.value = atTop;
  if (atTop) flushTraceBuffer();
}

function loadData() {
  refreshTimeRange();
  if (viewMode.value === "traces") loadTraces();
}

function selectPreset(preset: TimePreset) {
  customRange.value = null;
  customFromDate.value = "";
  customFromTime.value = "00:00";
  customToDate.value = "";
  customToTime.value = "23:59";
  activePreset.value = preset;
  liveMode.value = true;
  refreshTimeRange();
}

function setCustomRange(range: { from: string; to: string }) {
  customRange.value = range;
  liveMode.value = false;
  const f = new Date(range.from);
  const t = new Date(range.to);
  customFromDate.value = f.toISOString().slice(0, 10);
  customFromTime.value = f.toTimeString().slice(0, 5);
  customToDate.value = t.toISOString().slice(0, 10);
  customToTime.value = t.toTimeString().slice(0, 5);
  customRangeOpen.value = false;
  refreshTimeRange();
  loadData();
}

function applyCustomRange() {
  if (!customFromDate.value || !customToDate.value) return;
  setCustomRange({
    from: new Date(`${customFromDate.value}T${customFromTime.value}`).toISOString(),
    to: new Date(`${customToDate.value}T${customToTime.value}`).toISOString(),
  });
}

function switchView(mode: ViewMode) {
  viewMode.value = mode;
  selectedSpan.value = null;
}

function selectSpan(span: Span) {
  selectedSpan.value = span;
}

function closeDetail() {
  selectedSpan.value = null;
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(() => {
    if (viewMode.value === "traces") pollTraces();
  }, 5000);
}

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

watch(activePreset, () => {
  loadData();
});

watch(viewMode, () => {
  loadData();
});

watch(liveMode, (val) => {
  if (val) startPolling();
  else stopPolling();
});

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

function onClickOutsideCustomRange(e: MouseEvent) {
  const el = (e.target as HTMLElement).closest(".custom-range-selector");
  if (!el) customRangeOpen.value = false;
}

onMounted(() => {
  if (!contentGuid) return;
  refreshTimeRange();
  loadContentTitle();
  loadData();
  if (liveMode.value) startPolling();
  document.addEventListener("click", onClickOutsideCustomRange);
});

onUnmounted(() => {
  stopPolling();
  document.removeEventListener("click", onClickOutsideCustomRange);
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
    <header class="toolbar">
      <h1 class="content-title">{{ contentTitle }}</h1>
      <nav class="view-tabs">
        <button
          class="view-tab"
          :class="{ active: viewMode === 'traces' }"
          @click="switchView('traces')"
        >Traces</button>
        <button
          class="view-tab"
          :class="{ active: viewMode === 'logs' }"
          @click="switchView('logs')"
        >Logs</button>
      </nav>
      <div class="toolbar-right">
        <button
          class="live-btn"
          :class="{ active: liveMode }"
          @click="liveMode = !liveMode"
          title="Toggle live updates"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path
              d="M8 3v5l3.5 2"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <circle
              cx="8"
              cy="8"
              r="6.5"
              stroke="currentColor"
              stroke-width="1.5"
            />
          </svg>
        </button>
        <button class="refresh-btn" @click="loadData" title="Refresh">
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path
              d="M2.5 8a5.5 5.5 0 0 1 9.9-3.3M13.5 8a5.5 5.5 0 0 1-9.9 3.3"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
            />
            <path
              d="M12 1.5v3.5h-3.5M4 11h3.5v3.5"
              stroke="currentColor"
              stroke-width="1.5"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </button>
        <TimeFilter
          :presets="TIME_PRESETS"
          :active-preset="activePreset"
          @select="selectPreset"
        />
        <div class="custom-range-selector" @click.stop>
          <button class="custom-range-btn" :class="{ active: customRange }" @click="customRangeOpen = !customRangeOpen">
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
    </header>

    <TimelineHistogram v-if="viewMode === 'traces'" :groups="traceGroups" :time-range="timeRange" @custom-range="setCustomRange" />

    <div class="main-content" :class="{ 'with-detail': selectedSpan }">
      <TraceTable
        v-if="viewMode === 'traces'"
        :groups="traceGroups"
        :loading="loading"
        :loading-more="loadingMore"
        :has-more="hasMoreTraces"
        :total-traces="totalTraces"
        :selected-span="selectedSpan"
        :expanded-spans="expandedSpans"
        :is-at-top="tracesAtTop"
        :buffered-count="bufferedTraceGroups.length"
        :warn-traces="traceWarnMap"
        :live-mode="liveMode"
        @select-span="selectSpan"
        @toggle-expand="(id: string) => { expandedSpans.has(id) ? expandedSpans.delete(id) : expandedSpans.add(id) }"
        @scroll-state="onTracesScrollState"
        @load-more="loadMoreTraces"
      />
      <LogTable
        v-if="viewMode === 'logs'"
        :time-range="timeRange"
      />
      <SpanDetail
        v-if="selectedSpan && viewMode === 'traces'"
        :span="selectedSpan"
        @close="closeDetail"
      />
    </div>
  </div>
</template>

<style scoped>
.missing-guid {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  color: var(--gray-500);
  font-family: var(--font-sans);
  font-size: 16px;
  gap: 8px;
}

.missing-guid-hint {
  font-size: 13px;
  color: var(--gray-400);
}

.missing-guid code {
  background: var(--gray-100);
  padding: 2px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 12px;
}

.app-layout {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 16px;
  border-bottom: 1px solid var(--gray-200);
  background: #fff;
  gap: 12px;
  flex-shrink: 0;
}

.content-title {
  font-size: 15px;
  font-weight: 600;
  color: var(--gray-900);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  flex: 1;
}

.view-tabs {
  display: flex;
  align-items: center;
  gap: 0;
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  overflow: hidden;
  flex-shrink: 0;
}

.view-tab {
  padding: 5px 14px;
  font-size: 13px;
  font-weight: 500;
  font-family: var(--font-sans);
  border: none;
  background: #fff;
  color: var(--gray-500);
  cursor: pointer;
  transition: all 0.15s;
}

.view-tab:not(:last-child) {
  border-right: 1px solid var(--gray-200);
}

.view-tab:hover {
  background: var(--gray-50);
  color: var(--gray-700);
}

.view-tab.active {
  background: var(--blue-100);
  color: var(--blue-700);
  font-weight: 600;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.live-btn,
.refresh-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1px solid var(--gray-200);
  background: #fff;
  color: var(--gray-400);
  cursor: pointer;
  transition: all 0.15s;
}

.live-btn:hover,
.refresh-btn:hover {
  background: var(--blue-50);
  color: var(--blue-500);
  border-color: var(--blue-200);
}

.live-btn.active {
  background: var(--blue-100);
  color: var(--blue-500);
  border-color: var(--blue-400);
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.main-content.with-detail {
  display: flex;
}

.custom-range-selector {
  position: relative;
}

.custom-range-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: 20px;
  color: var(--gray-600);
  font-size: 14px;
  font-family: var(--font-sans);
  cursor: pointer;
  white-space: nowrap;
  transition: all 0.15s;
}

.custom-range-btn:hover {
  background: var(--blue-50);
  color: var(--blue-500);
  border-color: var(--blue-200);
}

.custom-range-btn.active {
  background: var(--blue-50);
  color: var(--blue-600);
  border-color: var(--blue-300);
  font-weight: 600;
}

.custom-range-dropdown {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  background: #fff;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
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
  color: var(--gray-500);
  min-width: 34px;
}

.date-picker,
.time-picker {
  padding: 5px 8px;
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
  border-radius: 4px;
  color: var(--gray-900);
  font-size: 12px;
  font-family: var(--font-mono);
}

.date-picker:focus,
.time-picker:focus {
  outline: none;
  border-color: var(--blue-400);
}

.apply-btn {
  padding: 6px 12px;
  background: var(--blue-500);
  color: #fff;
  border: none;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  font-family: var(--font-sans);
  cursor: pointer;
}

.apply-btn:hover:not(:disabled) {
  opacity: 0.9;
}

.apply-btn:disabled {
  opacity: 0.4;
  cursor: default;
}
</style>
