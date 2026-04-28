<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from "vue";
import type { Span } from "../types/traces";
import type { LogEntry } from "../types/logs";
import { withGuid, apiUrl } from "../guid";

const props = defineProps<{ span: Span }>();
const emit = defineEmits<{ close: [] }>();

const activeTab = ref<"details" | "raw">("details");
const contextLogs = ref<LogEntry[]>([]);
const logsLoading = ref(false);

interface MetricSample {
  timestamp: string;
  cpu_fraction: number;
  memory_bytes: number;
  connections: number | null;
}
const metricSamples = ref<MetricSample[]>([]);
const metricsLoading = ref(false);

async function loadMetrics() {
  metricsLoading.value = true;
  try {
    const from = new Date(props.span.startTime - 20000).toISOString();
    const to = new Date(props.span.endTime + 20000).toISOString();
    const qs = withGuid(new URLSearchParams({ from, to }));
    if (props.span.jobKey) qs.set("job_key", props.span.jobKey);
    const resp = await fetch(apiUrl(`/api/metrics?${qs}`));
    const data = await resp.json();
    metricSamples.value = data.samples ?? [];
  } catch {
    metricSamples.value = [];
  } finally {
    metricsLoading.value = false;
  }
}

async function loadContextLogs() {
  logsLoading.value = true;
  try {
    const from = new Date(props.span.startTime - 1000).toISOString();
    const to = new Date(props.span.endTime + 1000).toISOString();
    const qs = withGuid(new URLSearchParams({ from, to, limit: "500" }));
    if (props.span.jobKey) qs.set("job_key", props.span.jobKey);
    const resp = await fetch(apiUrl(`/api/logs?${qs}`));
    const data = await resp.json();
    const entries: LogEntry[] = data.entries ?? [];
    contextLogs.value = entries.filter(
      (e) => e.trace_id === props.span.traceId || e.span_id === props.span.spanId
    );
  } catch {
    contextLogs.value = [];
  } finally {
    logsLoading.value = false;
  }
}

watch(() => props.span.spanId, () => {
  loadContextLogs();
  loadMetrics();
}, { immediate: true });
const linkCopied = ref(false);
const panelWidth = ref(Math.round(window.innerWidth / 3));
const dragging = ref(false);

function onResizePointerDown(e: PointerEvent) {
  dragging.value = true;
  const target = e.target as HTMLElement;
  target.setPointerCapture(e.pointerId);
  document.body.style.cursor = "col-resize";
  document.body.style.userSelect = "none";
}

function onResizePointerMove(e: PointerEvent) {
  if (!dragging.value) return;
  const newWidth = window.innerWidth - e.clientX;
  panelWidth.value = Math.max(240, Math.min(newWidth, window.innerWidth * 0.8));
}

function onResizePointerUp() {
  dragging.value = false;
  document.body.style.cursor = "";
  document.body.style.userSelect = "";
}

function onWindowResize() {
  if (panelWidth.value > window.innerWidth * 0.8) {
    panelWidth.value = Math.round(window.innerWidth * 0.8);
  }
}

onMounted(() => window.addEventListener("resize", onWindowResize));
onUnmounted(() => window.removeEventListener("resize", onWindowResize));

function copyLink() {
  const url = new URL(window.location.href);
  url.searchParams.set("trace_id", props.span.traceId);
  url.searchParams.set("span_id", props.span.spanId);
  navigator.clipboard.writeText(url.toString()).then(() => {
    linkCopied.value = true;
    setTimeout(() => (linkCopied.value = false), 2000);
  });
}

function formatDuration(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatTimestamp(ms: number): string {
  const d = new Date(ms);
  const month = d.toLocaleString("en", { month: "short" });
  const day = d.getDate().toString().padStart(2, "0");
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  return `${month} ${day} ${h}:${m}:${s}`;
}

function statusLabel(code: number): string {
  if (code === 2) return "error";
  if (code === 1) return "ok";
  return "unset";
}

function levelLabel(code: number): string {
  if (code === 2) return "Error";
  if (code === 1) return "Info";
  return "Info";
}

const sortedAttributes = computed(() => {
  return Object.entries(props.span.attributes).sort((a, b) =>
    a[0].localeCompare(b[0])
  );
});

const codeSource = computed(() => {
  const file = props.span.attributes["code.filepath"] ?? "";
  const line = props.span.attributes["code.lineno"] ?? "";
  const func = props.span.attributes["code.function"] ?? "";
  if (!file) return null;
  return { file, line, func };
});

const arguments_ = computed(() => {
  const raw = props.span.attributes["logfire.msg_template"] ??
    props.span.attributes["logfire.json_schema"] ?? "";
  const args: Record<string, string> = {};
  for (const [k, v] of Object.entries(props.span.attributes)) {
    if (
      !k.startsWith("code.") &&
      !k.startsWith("logfire.") &&
      !k.startsWith("otel.") &&
      k !== "service.name" &&
      k !== "job.key"
    ) {
      args[k] = v;
    }
  }
  return args;
});

const CHART_W = 600;
const CHART_H = 80;
const CHART_PAD = { top: 4, bottom: 16, left: 0, right: 0 };

const metricsChartRange = computed(() => {
  const center = (props.span.startTime + props.span.endTime) / 2;
  return { from: center - 20000, to: center + 20000 };
});

function toX(ms: number): number {
  const { from, to } = metricsChartRange.value;
  return CHART_PAD.left + ((ms - from) / (to - from)) * (CHART_W - CHART_PAD.left - CHART_PAD.right);
}

const cpuPath = computed(() => {
  if (metricSamples.value.length < 2) return "";
  const maxCpu = Math.max(0.01, ...metricSamples.value.map((s) => s.cpu_fraction));
  const h = CHART_H - CHART_PAD.top - CHART_PAD.bottom;
  return metricSamples.value
    .map((s, i) => {
      const x = toX(new Date(s.timestamp).getTime());
      const y = CHART_PAD.top + h - (s.cpu_fraction / maxCpu) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join("");
});

const memPath = computed(() => {
  if (metricSamples.value.length < 2) return "";
  const maxMem = Math.max(1, ...metricSamples.value.map((s) => s.memory_bytes));
  const h = CHART_H - CHART_PAD.top - CHART_PAD.bottom;
  return metricSamples.value
    .map((s, i) => {
      const x = toX(new Date(s.timestamp).getTime());
      const y = CHART_PAD.top + h - (s.memory_bytes / maxMem) * h;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join("");
});

const spanMarkerX = computed(() => toX((props.span.startTime + props.span.endTime) / 2));

const spanRegion = computed(() => ({
  x1: toX(props.span.startTime),
  x2: toX(props.span.endTime),
}));

const metricsTimeLabels = computed(() => {
  const { from, to } = metricsChartRange.value;
  const count = 5;
  const labels: { text: string; x: number }[] = [];
  for (let i = 0; i <= count; i++) {
    const t = from + ((to - from) * i) / count;
    const d = new Date(t);
    const h = d.getHours().toString().padStart(2, "0");
    const m = d.getMinutes().toString().padStart(2, "0");
    const s = d.getSeconds().toString().padStart(2, "0");
    labels.push({ text: `${h}:${m}:${s}`, x: toX(t) });
  }
  return labels;
});

const cpuLabel = computed(() => {
  if (metricSamples.value.length === 0) return "";
  const max = Math.max(...metricSamples.value.map((s) => s.cpu_fraction));
  return `CPU (max ${(max * 100).toFixed(0)}%)`;
});

const memLabel = computed(() => {
  if (metricSamples.value.length === 0) return "";
  const max = Math.max(...metricSamples.value.map((s) => s.memory_bytes));
  if (max > 1e9) return `Mem (max ${(max / 1e9).toFixed(1)} GB)`;
  return `Mem (max ${(max / 1e6).toFixed(0)} MB)`;
});

function formatLogTime(ts: string): string {
  const d = new Date(ts);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  const ms = d.getMilliseconds().toString().padStart(3, "0");
  return `${h}:${m}:${s}.${ms}`;
}

function logSevClass(sev: string): string {
  if (sev === "error") return "log-sev-error";
  if (sev === "warn") return "log-sev-warn";
  return "";
}
</script>

<template>
  <div class="span-detail" :style="{ width: panelWidth + 'px' }">
    <div
      class="resize-handle"
      @pointerdown="onResizePointerDown"
      @pointermove="onResizePointerMove"
      @pointerup="onResizePointerUp"
    >
      <svg class="grip-icon" width="6" height="20" viewBox="0 0 6 20" fill="currentColor">
        <circle cx="1.5" cy="4" r="1.2" />
        <circle cx="4.5" cy="4" r="1.2" />
        <circle cx="1.5" cy="8" r="1.2" />
        <circle cx="4.5" cy="8" r="1.2" />
        <circle cx="1.5" cy="12" r="1.2" />
        <circle cx="4.5" cy="12" r="1.2" />
        <circle cx="1.5" cy="16" r="1.2" />
        <circle cx="4.5" cy="16" r="1.2" />
      </svg>
    </div>
    <div class="detail-inner">
    <div class="detail-header">
      <div class="header-top">
        <span class="header-label">message</span>
        <div class="header-actions">
          <span class="visibility-badge">Private</span>
          <button class="action-btn" title="Copy link" @click="copyLink">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path
                d="M6.5 9.5l3-3M9 6a2.5 2.5 0 0 1 0 3.5l-2 2a2.5 2.5 0 0 1-3.5-3.5l.5-.5M7 10a2.5 2.5 0 0 1 0-3.5l2-2a2.5 2.5 0 0 1 3.5 3.5l-.5.5"
                stroke="currentColor"
                stroke-width="1.2"
                stroke-linecap="round"
              />
            </svg>
          </button>
          <button class="close-btn" @click="emit('close')" title="Close">
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path
                d="M4 4l8 8M12 4l-8 8"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
              />
            </svg>
          </button>
        </div>
      </div>
      <h2 class="span-title">{{ span.name }}</h2>
      <div class="span-pills">
        <span class="pill">span_name <strong>{{ span.name }}</strong></span>
        <span class="pill" v-if="span.scope">
          otel_scope_name <strong>{{ span.scope }}</strong>
        </span>
        <span class="pill level" :class="'level-' + statusLabel(span.statusCode)">
          level <strong>{{ levelLabel(span.statusCode) }}</strong>
        </span>
        <span class="pill" v-if="span.serviceName">
          service_name <strong>{{ span.serviceName }}</strong>
        </span>
      </div>
      <div class="span-ids">
        <span class="id-item">kind <strong>span</strong></span>
        <span class="id-item">
          trace_id <strong class="mono">...{{ span.traceId.slice(-6) }}</strong>
        </span>
        <span class="id-item">
          span_id <strong class="mono">...{{ span.spanId.slice(-6) }}</strong>
        </span>
      </div>
      <div class="span-timing">
        Span took {{ formatDuration(span.duration) }} at {{ formatTimestamp(span.startTime) }}
      </div>
    </div>

    <div class="detail-tabs">
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'details' }"
        @click="activeTab = 'details'"
      >
        Details
      </button>
      <button
        class="tab-btn"
        :class="{ active: activeTab === 'raw' }"
        @click="activeTab = 'raw'"
      >
        Raw Data
      </button>
    </div>

    <div class="detail-content">
      <template v-if="activeTab === 'details'">
        <div v-if="codeSource" class="source-section">
          <div class="source-link">
            <span class="source-dot" />
            <span class="source-text mono">
              {{ codeSource.file }}:{{ codeSource.line }}
            </span>
            <span class="source-func mono">in {{ codeSource.func }}</span>
          </div>
        </div>

        <div v-if="Object.keys(arguments_).length > 0" class="attr-section">
          <h3 class="section-title">Arguments: (as Python)</h3>
          <pre class="attr-block mono">{{ JSON.stringify(arguments_, null, 2) }}</pre>
        </div>

        <details class="attr-section" open>
          <summary class="section-title clickable">Attributes</summary>
          <table class="attr-table" v-if="sortedAttributes.length > 0">
            <tr v-for="[key, val] in sortedAttributes" :key="key">
              <td class="attr-key mono">{{ key }}</td>
              <td class="attr-val mono">{{ val }}</td>
            </tr>
          </table>
          <div v-else class="empty-attrs">No attributes</div>
        </details>

        <details v-if="span.events.length > 0" class="attr-section">
          <summary class="section-title clickable">Events ({{ span.events.length }})</summary>
          <div v-for="(evt, i) in span.events" :key="i" class="event-item">
            <strong class="mono">{{ evt.name }}</strong>
            <div v-for="a in evt.attributes" :key="a.key" class="event-attr">
              <span class="attr-key mono">{{ a.key }}:</span>
              <span class="attr-val mono">{{ a.value.stringValue ?? a.value.intValue ?? "" }}</span>
            </div>
          </div>
        </details>

        <details class="attr-section" open>
          <summary class="section-title clickable">
            Context Logs ({{ logsLoading ? "..." : contextLogs.length }})
          </summary>
          <div v-if="logsLoading" class="context-logs-loading">Loading...</div>
          <div v-else-if="contextLogs.length === 0" class="empty-attrs">
            No log entries found for this span
          </div>
          <div v-else class="context-logs">
            <div
              v-for="(log, i) in contextLogs"
              :key="i"
              class="context-log-row"
              :class="logSevClass(log.severity)"
            >
              <span class="context-log-source" :class="'src-' + log.source">{{ log.source }}</span>
              <span class="context-log-time mono">{{ formatLogTime(log.timestamp) }}</span>
              <span class="context-log-body mono">{{ log.body }}</span>
            </div>
          </div>
        </details>

        <details class="attr-section" open>
          <summary class="section-title clickable">Metrics</summary>
          <div v-if="metricsLoading" class="context-logs-loading">Loading...</div>
          <div v-else-if="metricSamples.length === 0" class="empty-attrs">
            No metric samples found for this span window
          </div>
          <div v-else class="metrics-chart-wrapper">
            <div class="metrics-legend">
              <span class="legend-item legend-cpu">
                <span class="legend-swatch" />
                {{ cpuLabel }}
              </span>
              <span class="legend-item legend-mem">
                <span class="legend-swatch" />
                {{ memLabel }}
              </span>
            </div>
            <svg
              class="metrics-chart"
              :viewBox="`0 0 ${CHART_W} ${CHART_H}`"
              preserveAspectRatio="none"
            >
              <rect
                :x="spanRegion.x1"
                :y="0"
                :width="Math.max(1, spanRegion.x2 - spanRegion.x1)"
                :height="CHART_H"
                class="span-band"
              />
              <line
                :x1="spanMarkerX" :y1="0"
                :x2="spanMarkerX" :y2="CHART_H - CHART_PAD.bottom"
                class="span-center-line"
              />
              <path v-if="cpuPath" :d="cpuPath" class="line-cpu" />
              <path v-if="memPath" :d="memPath" class="line-mem" />
              <text
                v-for="(lbl, i) in metricsTimeLabels"
                :key="i"
                :x="lbl.x"
                :y="CHART_H - 2"
                class="time-label"
              >{{ lbl.text }}</text>
            </svg>
          </div>
        </details>
      </template>

      <template v-else>
        <pre class="raw-json mono">{{ JSON.stringify(span, null, 2) }}</pre>
      </template>
    </div>
    </div>
  </div>
</template>

<style scoped>
.span-detail {
  flex-shrink: 0;
  position: relative;
  background: #fff;
  display: flex;
  flex-direction: row;
  overflow: hidden;
}

.resize-handle {
  width: 12px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: col-resize;
  background: var(--gray-50);
  border-left: 1px solid var(--gray-200);
  border-right: 1px solid var(--gray-200);
  color: var(--gray-300);
  transition: all 0.15s;
}

.resize-handle:hover {
  background: var(--blue-50);
  border-left-color: var(--blue-300);
  border-right-color: var(--blue-300);
  color: var(--blue-500);
}

.resize-handle:active {
  background: var(--blue-100);
  color: var(--blue-500);
}

.grip-icon {
  pointer-events: none;
}

.detail-inner {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  overflow: hidden;
}

.detail-header {
  padding: 12px 16px;
  border-bottom: 1px solid var(--gray-200);
}

.header-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}

.header-label {
  font-size: 12px;
  color: var(--gray-400);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}

.visibility-badge {
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--gray-100);
  color: var(--gray-600);
}

.action-btn,
.close-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: none;
  color: var(--gray-400);
  cursor: pointer;
  border-radius: 4px;
  transition: all 0.15s;
}

.action-btn:hover,
.close-btn:hover {
  background: var(--gray-100);
  color: var(--gray-700);
}

.span-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--gray-900);
  margin-bottom: 8px;
}

.span-pills {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 8px;
}

.pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border-radius: 4px;
  font-size: 11px;
  color: var(--gray-500);
  background: var(--gray-50);
  border: 1px solid var(--gray-200);
}

.pill strong {
  color: var(--gray-900);
  font-weight: 500;
}

.pill.level-error {
  background: var(--red-50);
  border-color: var(--red-300);
}

.pill.level-error strong {
  color: var(--red-600);
}

.span-ids {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 8px;
}

.id-item {
  font-size: 11px;
  color: var(--gray-400);
}

.id-item strong {
  color: var(--gray-600);
  font-weight: 500;
}

.span-timing {
  font-size: 12px;
  color: var(--gray-500);
}

.detail-tabs {
  display: flex;
  border-bottom: 1px solid var(--gray-200);
  flex-shrink: 0;
}

.tab-btn {
  padding: 8px 16px;
  font-size: 13px;
  font-family: var(--font-sans);
  background: none;
  border: none;
  color: var(--gray-400);
  cursor: pointer;
  transition: all 0.15s;
  font-weight: 500;
}

.tab-btn.active {
  color: var(--gray-900);
  box-shadow: inset 0 -2px 0 var(--blue-500);
}

.detail-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px 16px;
}

.source-section {
  margin-bottom: 16px;
}

.source-link {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-radius: 6px;
  background: var(--gray-50);
}

.source-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--green-500);
  flex-shrink: 0;
}

.source-text {
  font-size: 13px;
  color: var(--gray-900);
}

.source-func {
  font-size: 13px;
  color: var(--gray-400);
}

.attr-section {
  margin-bottom: 12px;
}

.section-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--gray-700);
  margin-bottom: 8px;
}

.section-title.clickable {
  cursor: pointer;
}

.attr-block {
  font-size: 13px;
  padding: 12px;
  background: var(--gray-50);
  border-radius: 6px;
  border: 1px solid var(--gray-200);
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}

.attr-table {
  width: 100%;
  border-collapse: collapse;
}

.attr-table tr {
  border-bottom: 1px solid var(--gray-100);
}

.attr-table td {
  padding: 4px 8px;
  font-size: 12px;
  vertical-align: top;
}

.attr-key {
  color: var(--gray-500);
  white-space: nowrap;
  width: 40%;
}

.attr-val {
  color: var(--gray-900);
  word-break: break-all;
}

.empty-attrs {
  color: var(--gray-400);
  font-size: 13px;
  padding: 8px;
}

.event-item {
  padding: 8px;
  margin-bottom: 4px;
  border-radius: 4px;
  background: var(--gray-50);
}

.event-attr {
  font-size: 12px;
  margin-top: 2px;
}

.raw-json {
  font-size: 12px;
  padding: 12px;
  background: var(--gray-50);
  border-radius: 6px;
  border: 1px solid var(--gray-200);
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;
  max-height: 100%;
}

.context-logs {
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  overflow: hidden;
}

.context-log-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 4px 8px;
  font-size: 12px;
  border-bottom: 1px solid var(--gray-100);
}

.context-log-row:last-child {
  border-bottom: none;
}

.context-log-row:hover {
  background: var(--gray-50);
}

.context-log-row.log-sev-error {
  background: var(--red-50);
}

.context-log-row.log-sev-warn {
  background: var(--orange-50);
}

.context-log-source {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-family: var(--font-mono);
  font-size: 10px;
  white-space: nowrap;
  flex-shrink: 0;
}

.context-log-source.src-stdout {
  background: var(--green-100);
  color: var(--green-800);
}

.context-log-source.src-stderr {
  background: var(--red-100);
  color: var(--red-700);
}

.context-log-source.src-otel {
  background: var(--otel-bg);
  color: var(--otel-text);
}

.context-log-time {
  color: var(--gray-400);
  font-size: 11px;
  white-space: nowrap;
  flex-shrink: 0;
}

.context-log-body {
  color: var(--gray-900);
  word-break: break-all;
  min-width: 0;
}

.context-logs-loading {
  color: var(--gray-400);
  font-size: 13px;
  padding: 8px;
}

.mono {
  font-family: var(--font-mono);
}

.metrics-chart-wrapper {
  border: 1px solid var(--gray-200);
  border-radius: 6px;
  padding: 8px;
  background: var(--gray-50);
}

.metrics-legend {
  display: flex;
  gap: 16px;
  margin-bottom: 6px;
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--gray-600);
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.legend-swatch {
  width: 10px;
  height: 3px;
  border-radius: 1px;
}

.legend-cpu .legend-swatch {
  background: var(--blue-500);
}

.legend-mem .legend-swatch {
  background: var(--purple-500, #8b5cf6);
}

.metrics-chart {
  width: 100%;
  height: 80px;
  display: block;
}

.span-band {
  fill: var(--blue-100);
  opacity: 0.5;
}

.span-center-line {
  stroke: var(--blue-400);
  stroke-width: 1;
  stroke-dasharray: 3 2;
}

.line-cpu {
  fill: none;
  stroke: var(--blue-500);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.line-mem {
  fill: none;
  stroke: var(--purple-500, #8b5cf6);
  stroke-width: 1.5;
  vector-effect: non-scaling-stroke;
}

.time-label {
  font-size: 9px;
  font-family: var(--font-mono);
  fill: var(--gray-400);
  text-anchor: middle;
}
</style>
