<script setup lang="ts">
import { ref, inject, computed, onMounted } from "vue";
import type { Ref } from "vue";
import { useRoute, useRouter } from "vue-router";
import type { Span, TraceGroup } from "../types/traces";
import type { LogEntry } from "../types/logs";
import { fetchTraceSpans, fetchLogs, buildTraceGroups } from "../api/client";
import { withGuid, apiUrl } from "../guid";

const route = useRoute();
const router = useRouter();
const setupRequired = inject<Ref<boolean>>("setupRequired")!;
const traceId = route.params.traceId as string;

const group = ref<TraceGroup | null>(null);
const loading = ref(true);
const selectedSpan = ref<Span | null>(null);
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

const spanLogSeverities = ref(new Map<string, Set<string>>());

function spanHasWarn(spanId: string): boolean {
  return spanLogSeverities.value.get(spanId)?.has("warn") ?? false;
}

const totalSpans = computed(() => group.value?.spans.length ?? 0);
const errorSpans = computed(() => group.value?.spans.filter((s) => s.statusCode === 2).length ?? 0);

const serviceBreakdown = computed(() => {
  if (!group.value) return [];
  const byService = new Map<string, number>();
  let total = 0;
  for (const s of group.value.spans) {
    const name = s.serviceName || "unknown";
    byService.set(name, (byService.get(name) ?? 0) + s.duration);
    total += s.duration;
  }
  return [...byService.entries()]
    .map(([name, dur]) => ({ name, pct: total > 0 ? (dur / total) * 100 : 0 }))
    .sort((a, b) => b.pct - a.pct);
});

const SERVICE_COLORS = ["#447099", "#72994e", "#ee6331", "#d44000", "#7c3aed", "#305775", "#80361c", "#a2b8cb"];
function serviceColor(name: string): string {
  const services = serviceBreakdown.value;
  const idx = services.findIndex((s) => s.name === name);
  return SERVICE_COLORS[idx % SERVICE_COLORS.length];
}

interface FlatSpan {
  span: Span;
  depth: number;
  childCount: number;
  hasChildren: boolean;
  expanded: boolean;
}

function countDescendants(span: Span): number {
  let n = 0;
  for (const c of span.children) n += 1 + countDescendants(c);
  return n;
}

const collapsed = ref(new Set<string>());

function toggleCollapse(spanId: string) {
  const s = new Set(collapsed.value);
  if (s.has(spanId)) s.delete(spanId);
  else s.add(spanId);
  collapsed.value = s;
}

const flatSpans = computed<FlatSpan[]>(() => {
  if (!group.value) return [];
  const result: FlatSpan[] = [];
  const collapsedSet = collapsed.value;

  function walk(span: Span, depth: number) {
    const hasChildren = span.children.length > 0;
    const expanded = !collapsedSet.has(span.spanId);
    result.push({ span, depth, childCount: countDescendants(span), hasChildren, expanded });
    if (hasChildren && expanded) {
      for (const c of span.children) walk(c, depth + 1);
    }
  }

  walk(group.value.rootSpan, 0);
  return result;
});

const traceStart = computed(() => group.value?.startTime ?? 0);
const traceDuration = computed(() => group.value?.duration ?? 1);

const timeLabels = computed(() => {
  const dur = traceDuration.value;
  const count = 8;
  const labels: { text: string; left: number }[] = [];
  for (let i = 0; i <= count; i++) {
    const ms = (dur * i) / count;
    labels.push({ text: formatDurationShort(ms), left: (i / count) * 100 });
  }
  return labels;
});

function barLeft(span: Span): number {
  return ((span.startTime - traceStart.value) / traceDuration.value) * 100;
}

function barWidth(span: Span): number {
  return Math.max(0.3, (span.duration / traceDuration.value) * 100);
}

function formatDuration(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(2)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatDurationShort(ms: number): string {
  if (ms === 0) return "0s";
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

function formatTime(ms: number): string {
  const d = new Date(ms);
  const month = d.toLocaleString("en", { month: "short" });
  const day = d.getDate().toString().padStart(2, "0");
  const year = d.getFullYear();
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  return `${month} ${day}, ${year} -- ${h}:${m}:${s}`;
}

function selectSpan(span: Span) {
  selectedSpan.value = span;
  loadContextLogs(span);
  loadMetrics(span);
}

async function loadContextLogs(span: Span) {
  logsLoading.value = true;
  try {
    const from = new Date(span.startTime - 1000).toISOString();
    const to = new Date(span.endTime + 1000).toISOString();
    const qs = withGuid(new URLSearchParams({ from, to, limit: "500" }));
    if (span.jobKey) qs.set("job_key", span.jobKey);
    const resp = await fetch(apiUrl(`/api/logs?${qs}`));
    const data = await resp.json();
    const entries: LogEntry[] = data.entries ?? [];
    contextLogs.value = entries.filter(
      (e) => e.trace_id === span.traceId || e.span_id === span.spanId
    );
  } catch {
    contextLogs.value = [];
  } finally {
    logsLoading.value = false;
  }
}

async function loadMetrics(span: Span) {
  metricsLoading.value = true;
  try {
    const from = new Date(span.startTime - 20000).toISOString();
    const to = new Date(span.endTime + 20000).toISOString();
    const qs = withGuid(new URLSearchParams({ from, to }));
    if (span.jobKey) qs.set("job_key", span.jobKey);
    const resp = await fetch(apiUrl(`/api/metrics?${qs}`));
    const data = await resp.json();
    metricSamples.value = data.samples ?? [];
  } catch {
    metricSamples.value = [];
  } finally {
    metricsLoading.value = false;
  }
}

const CHART_W = 500;
const CHART_H = 80;

const metricsChartRange = computed(() => {
  if (!selectedSpan.value) return { from: 0, to: 1 };
  const center = (selectedSpan.value.startTime + selectedSpan.value.endTime) / 2;
  return { from: center - 20000, to: center + 20000 };
});

function toX(ms: number): number {
  const { from, to } = metricsChartRange.value;
  return ((ms - from) / (to - from)) * CHART_W;
}

const cpuPath = computed(() => {
  if (metricSamples.value.length < 2) return "";
  const plotH = chartPlotBottom.value - chartPlotTop;
  const maxCpu = Math.max(0.01, ...metricSamples.value.map((s) => s.cpu_fraction));
  return metricSamples.value
    .map((s, i) => {
      const x = toX(new Date(s.timestamp).getTime());
      const y = chartPlotTop + plotH - (s.cpu_fraction / maxCpu) * plotH;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join("");
});

const memPath = computed(() => {
  if (metricSamples.value.length < 2) return "";
  const plotH = chartPlotBottom.value - chartPlotTop;
  const maxMem = Math.max(1, ...metricSamples.value.map((s) => s.memory_bytes));
  return metricSamples.value
    .map((s, i) => {
      const x = toX(new Date(s.timestamp).getTime());
      const y = chartPlotTop + plotH - (s.memory_bytes / maxMem) * plotH;
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    }).join("");
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

const spanBandX1 = computed(() => {
  if (!selectedSpan.value) return 0;
  return toX(selectedSpan.value.startTime);
});

const spanBandX2 = computed(() => {
  if (!selectedSpan.value) return 0;
  return toX(selectedSpan.value.endTime);
});

const chartPlotTop = 4;
const chartPlotBottom = computed(() => CHART_H - 16);

function formatChartTime(ms: number): string {
  const d = new Date(ms);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

const chartTimeLabels = computed(() => {
  const { from, to } = metricsChartRange.value;
  const count = 5;
  const labels: { text: string; x: number }[] = [];
  for (let i = 0; i <= count; i++) {
    const ms = from + ((to - from) * i) / count;
    labels.push({ text: formatChartTime(ms), x: (i / count) * CHART_W });
  }
  return labels;
});

function formatLogTime(ts: string): string {
  const d = new Date(ts);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  const ms = d.getMilliseconds().toString().padStart(3, "0");
  return `${h}:${m}:${s}.${ms}`;
}

const sortedAttributes = computed(() => {
  if (!selectedSpan.value) return [];
  return Object.entries(selectedSpan.value.attributes).sort((a, b) => a[0].localeCompare(b[0]));
});

const detailTab = ref<"attributes" | "events" | "logs" | "metrics">("attributes");

onMounted(async () => {
  loading.value = true;
  try {
    const { spans } = await fetchTraceSpans({ traceId, limit: 1000 });
    if (spans.length === 0) return;
    const fresh = spans.map((s) => ({ ...s, children: [] as Span[], depth: 0 }));
    const groups = buildTraceGroups(fresh);
    group.value = groups.find((g) => g.traceId === traceId) ?? groups[0] ?? null;

    if (group.value) {
      const from = new Date(group.value.startTime - 1000).toISOString();
      const to = new Date(group.value.endTime + 1000).toISOString();
      const { entries } = await fetchLogs({ from, to, limit: 1000 });
      const sevMap = new Map<string, Set<string>>();
      for (const log of entries) {
        if (log.span_id && (log.severity === "warn" || log.severity === "error")) {
          let set = sevMap.get(log.span_id);
          if (!set) { set = new Set(); sevMap.set(log.span_id, set); }
          set.add(log.severity);
        }
      }
      spanLogSeverities.value = sevMap;
    }
  } catch (e: any) {
    if (e?.message === "SETUP_REQUIRED") {
      setupRequired.value = true;
      return;
    }
    throw e;
  } finally {
    loading.value = false;
  }
});
</script>

<template>
  <div class="detail-view">
    <div class="detail-top-bar">
      <button class="back-btn" @click="router.back()">
        <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
          <path d="M10 3L5 8l5 5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
        </svg>
      </button>
      <span class="trace-id-label">Trace ID</span>
      <span class="trace-id-value mono">{{ traceId }}</span>
      <template v-if="group">
        <span class="sep">--</span>
        <span class="root-service">{{ group.rootSpan.serviceName }}</span>
        <span class="sep">--</span>
        <span class="root-op mono">{{ group.rootSpan.name }}</span>
        <span class="duration-badge">{{ formatDuration(group.duration) }}</span>
        <span class="timestamp">{{ formatTime(group.startTime) }}</span>
      </template>
    </div>

    <div v-if="loading" class="loading-state">Loading trace...</div>
    <div v-else-if="!group" class="empty-state">Trace not found.</div>

    <template v-else>
      <div class="summary-cards">
        <div class="card">
          <div class="card-label">Total Spans</div>
          <div class="card-value">{{ totalSpans }}</div>
        </div>
        <div class="card card-error">
          <div class="card-label">Error Spans</div>
          <div class="card-value">{{ errorSpans }}</div>
        </div>
      </div>

      <div class="flamegraph-area">
        <div class="waterfall-area">
          <div class="time-axis-row">
            <div class="time-axis-spacer" />
            <div class="time-axis">
              <span v-for="l in timeLabels" :key="l.left" class="time-tick" :style="{ left: l.left + '%' }">{{ l.text }}</span>
            </div>
          </div>
          <div class="waterfall-rows">
            <div
              v-for="fs in flatSpans"
              :key="fs.span.spanId"
              class="waterfall-row"
              :class="{ selected: selectedSpan?.spanId === fs.span.spanId, 'row-error': fs.span.statusCode === 2, 'row-warn': fs.span.statusCode !== 2 && spanHasWarn(fs.span.spanId) }"
              @click="selectSpan(fs.span)"
            >
              <div class="row-label" :style="{ paddingLeft: fs.depth * 20 + 8 + 'px' }">
                <div class="row-toggle-line">
                  <button
                    v-if="fs.hasChildren"
                    class="toggle-btn"
                    @click.stop="toggleCollapse(fs.span.spanId)"
                  >
                    <svg width="10" height="10" viewBox="0 0 10 10">
                      <path v-if="fs.expanded" d="M2 3l3 3 3-3" fill="none" stroke="currentColor" stroke-width="1.2" />
                      <path v-else d="M3 2l3 3-3 3" fill="none" stroke="currentColor" stroke-width="1.2" />
                    </svg>
                  </button>
                  <span v-if="fs.hasChildren" class="child-count">{{ fs.childCount }}</span>
                  <span v-else class="toggle-leaf" />
                  <span class="row-name mono">{{ fs.span.name }}</span>
                </div>
                <div class="row-service-line" :style="{ paddingLeft: fs.hasChildren ? '0' : '18px' }">
                  <span class="depth-bar" :style="{ background: serviceColor(fs.span.serviceName) }" />
                  <span class="row-service">{{ fs.span.serviceName }}</span>
                </div>
              </div>
              <div class="row-bar-area">
                <div
                  class="span-bar"
                  :class="{ error: fs.span.statusCode === 2, ongoing: fs.span.ongoing }"
                  :style="{
                    left: barLeft(fs.span) + '%',
                    width: barWidth(fs.span) + '%',
                    background: fs.span.statusCode === 2 ? 'var(--accent-red)' : serviceColor(fs.span.serviceName),
                  }"
                />
                <span class="bar-duration mono" :style="{ left: (barLeft(fs.span) + barWidth(fs.span) + 0.5) + '%' }">{{ formatDuration(fs.span.duration) }}</span>
              </div>
            </div>
          </div>
        </div>

        <div v-if="selectedSpan" class="span-detail-panel">
          <div class="panel-header">
            <span>Span Details</span>
            <button class="panel-close" @click="selectedSpan = null">
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
              </svg>
            </button>
          </div>
          <div class="panel-body">
            <div class="detail-field">
              <span class="field-label">SPAN NAME</span>
              <span class="field-value mono">{{ selectedSpan.name }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">SPAN ID</span>
              <span class="field-value mono">{{ selectedSpan.spanId }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">START TIME</span>
              <span class="field-value">{{ formatTime(selectedSpan.startTime) }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">DURATION</span>
              <span class="field-value mono">{{ formatDuration(selectedSpan.duration) }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">SERVICE</span>
              <span class="field-value">{{ selectedSpan.serviceName || "unknown" }}</span>
            </div>
            <div class="detail-field">
              <span class="field-label">STATUS</span>
              <span class="field-value" :class="{ 'status-error': selectedSpan.statusCode === 2 }">
                {{ selectedSpan.statusCode === 2 ? "Error" : selectedSpan.statusCode === 1 ? "Ok" : "Unset" }}
              </span>
            </div>

            <div class="panel-tabs">
              <button :class="{ active: detailTab === 'attributes' }" @click="detailTab = 'attributes'">Attributes {{ sortedAttributes.length }}</button>
              <button :class="{ active: detailTab === 'events' }" @click="detailTab = 'events'">Events {{ selectedSpan.events.length }}</button>
              <button :class="{ active: detailTab === 'logs' }" @click="detailTab = 'logs'">Logs {{ contextLogs.length }}</button>
              <button :class="{ active: detailTab === 'metrics' }" @click="detailTab = 'metrics'">Metrics</button>
            </div>

            <div v-if="detailTab === 'attributes'" class="tab-content">
              <div v-for="[key, val] in sortedAttributes" :key="key" class="attr-row">
                <span class="attr-key mono">{{ key }}</span>
                <span class="attr-val mono">{{ val }}</span>
              </div>
              <div v-if="sortedAttributes.length === 0" class="tab-empty">No attributes</div>
            </div>

            <div v-if="detailTab === 'events'" class="tab-content">
              <div v-for="(evt, i) in selectedSpan.events" :key="i" class="event-item">
                <div class="event-name mono">{{ evt.name }}</div>
                <div v-for="a in evt.attributes" :key="a.key" class="attr-row">
                  <span class="attr-key mono">{{ a.key }}</span>
                  <span class="attr-val mono">{{ a.value.stringValue ?? a.value.intValue ?? "" }}</span>
                </div>
              </div>
              <div v-if="selectedSpan.events.length === 0" class="tab-empty">No events</div>
            </div>

            <div v-if="detailTab === 'logs'" class="tab-content">
              <div v-if="logsLoading" class="tab-empty">Loading...</div>
              <div v-else-if="contextLogs.length === 0" class="tab-empty">No logs found for this span</div>
              <div v-else>
                <div v-for="(log, i) in contextLogs" :key="i" class="log-row">
                  <span class="log-source" :class="'src-' + log.source">{{ log.source }}</span>
                  <span class="log-time mono">{{ formatLogTime(log.timestamp) }}</span>
                  <span class="log-body mono">{{ log.body }}</span>
                </div>
              </div>
            </div>

            <div v-if="detailTab === 'metrics'" class="tab-content">
              <div v-if="metricsLoading" class="tab-empty">Loading...</div>
              <div v-else-if="metricSamples.length === 0" class="tab-empty">No metrics for this span window</div>
              <div v-else class="metrics-chart-area">
                <div class="metrics-legend">
                  <span class="legend-cpu"><span class="legend-dot" /> {{ cpuLabel }}</span>
                  <span class="legend-mem"><span class="legend-dot" /> {{ memLabel }}</span>
                </div>
                <svg class="metrics-svg" :viewBox="`0 0 ${CHART_W} ${CHART_H}`">
                  <!-- span time band -->
                  <rect
                    :x="spanBandX1"
                    :y="chartPlotTop"
                    :width="Math.max(1, spanBandX2 - spanBandX1)"
                    :height="chartPlotBottom - chartPlotTop"
                    fill="var(--accent-blue)"
                    opacity="0.1"
                  />
                  <line :x1="spanBandX1" :x2="spanBandX1" :y1="chartPlotTop" :y2="chartPlotBottom" stroke="var(--accent-blue)" stroke-width="1" stroke-dasharray="3,2" />
                  <line :x1="spanBandX2" :x2="spanBandX2" :y1="chartPlotTop" :y2="chartPlotBottom" stroke="var(--accent-blue)" stroke-width="1" stroke-dasharray="3,2" />
                  <!-- data lines -->
                  <path v-if="cpuPath" :d="cpuPath" fill="none" stroke="var(--accent-blue)" stroke-width="1.5" vector-effect="non-scaling-stroke" />
                  <path v-if="memPath" :d="memPath" fill="none" stroke="var(--accent-purple)" stroke-width="1.5" vector-effect="non-scaling-stroke" />
                  <!-- time axis -->
                  <line :x1="0" :x2="CHART_W" :y1="chartPlotBottom" :y2="chartPlotBottom" stroke="var(--border)" stroke-width="0.5" />
                  <template v-for="l in chartTimeLabels" :key="l.x">
                    <line :x1="l.x" :x2="l.x" :y1="chartPlotBottom" :y2="chartPlotBottom + 3" stroke="var(--text-muted)" stroke-width="0.5" />
                    <text :x="l.x" :y="CHART_H - 2" text-anchor="middle" fill="var(--text-muted)" font-size="8" font-family="var(--font-mono)">{{ l.text }}</text>
                  </template>
                </svg>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.detail-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  overflow: hidden;
}

.detail-top-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  flex-wrap: wrap;
}

.back-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 4px;
  border: 1px solid var(--border);
  background: var(--bg-elevated);
  color: var(--text-secondary);
  cursor: pointer;
}

.back-btn:hover {
  background: var(--bg-hover);
  color: var(--text-primary);
}

.trace-id-label {
  font-size: 11px;
  color: var(--text-muted);
}

.trace-id-value {
  font-size: 12px;
  color: var(--accent-blue);
}

.sep {
  color: var(--text-muted);
  font-size: 12px;
}

.root-service,
.root-op {
  font-size: 12px;
  color: var(--text-secondary);
}

.duration-badge {
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--bg-elevated);
  border: 1px solid var(--border);
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-secondary);
}

.timestamp {
  font-size: 11px;
  color: var(--text-muted);
}

.mono {
  font-family: var(--font-mono);
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

.summary-cards {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  flex-shrink: 0;
}

.card {
  padding: 10px 20px;
  background: var(--bg-secondary);
  border: 1px solid var(--border);
  border-radius: 6px;
  min-width: 120px;
}

.card-label {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.card-value {
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
}

.card-error .card-value {
  color: var(--accent-red);
}

.flamegraph-area {
  flex: 1;
  display: flex;
  overflow: hidden;
  min-height: 0;
}

.service-panel {
  width: 200px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  background: var(--bg-secondary);
  padding: 8px 0;
  overflow-y: auto;
}

.service-panel-header {
  padding: 4px 12px;
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.service-row {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 12px;
  font-size: 12px;
}

.service-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.service-name {
  color: var(--text-secondary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.service-pct {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
}

.waterfall-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
  overflow: hidden;
}

.time-axis-row {
  display: flex;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.time-axis-spacer {
  width: 260px;
  flex-shrink: 0;
}

.time-axis {
  position: relative;
  height: 24px;
  flex: 1;
  min-width: 0;
  overflow: visible;
  margin-right: 60px;
}

.time-tick {
  position: absolute;
  top: 6px;
  transform: translateX(-50%);
  font-size: 10px;
  font-family: var(--font-mono);
  color: var(--text-muted);
  white-space: nowrap;
}

.waterfall-rows {
  flex: 1;
  overflow-y: auto;
}

.waterfall-row {
  display: flex;
  align-items: stretch;
  min-height: 44px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.1s;
}

.waterfall-row:hover {
  background: var(--bg-hover);
}

.waterfall-row.selected {
  background: var(--bg-active);
}

.waterfall-row.row-error {
  background: var(--accent-red-dim);
}

.waterfall-row.row-warn {
  background: var(--accent-warn-dim);
}

.row-label {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 1px;
  overflow: hidden;
  padding-right: 8px;
}

.row-toggle-line {
  display: flex;
  align-items: center;
  gap: 4px;
}

.toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
  flex-shrink: 0;
}

.toggle-btn:hover {
  color: var(--text-primary);
}

.toggle-leaf {
  width: 16px;
  flex-shrink: 0;
}

.child-count {
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  min-width: 12px;
  flex-shrink: 0;
}

.row-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-service-line {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: 20px;
}

.depth-bar {
  width: 3px;
  height: 12px;
  border-radius: 1px;
  flex-shrink: 0;
}

.row-service {
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.row-bar-area {
  flex: 1;
  position: relative;
  height: auto;
  min-width: 0;
  display: flex;
  align-items: center;
  margin-right: 60px;
}

.span-bar {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  height: 14px;
  border-radius: 3px;
  min-width: 3px;
}

.span-bar.ongoing {
  background-image: repeating-linear-gradient(
    -45deg, transparent, transparent 3px, rgba(255,255,255,0.1) 3px, rgba(255,255,255,0.1) 6px
  ) !important;
}

.bar-duration {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  font-size: 11px;
  color: var(--text-secondary);
  white-space: nowrap;
}

.span-detail-panel {
  width: 680px;
  flex-shrink: 0;
  border-left: 1px solid var(--border);
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  font-size: 13px;
  font-weight: 600;
}

.panel-close {
  display: inline-flex;
  align-items: center;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
}

.panel-close:hover {
  color: var(--text-primary);
}

.panel-body {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.detail-field {
  margin-bottom: 12px;
}

.field-label {
  display: block;
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.5px;
  margin-bottom: 3px;
}

.field-value {
  font-size: 13px;
  color: var(--text-primary);
  word-break: break-all;
}

.status-error {
  color: var(--accent-red);
}

.panel-tabs {
  display: flex;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
  gap: 0;
}

.panel-tabs button {
  padding: 6px 10px;
  font-size: 11px;
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  white-space: nowrap;
}

.panel-tabs button.active {
  color: var(--text-primary);
  border-bottom-color: var(--accent-blue);
}

.tab-content {
  font-size: 12px;
}

.tab-empty {
  color: var(--text-muted);
  font-size: 12px;
  padding: 8px 0;
}

.attr-row {
  display: flex;
  flex-direction: column;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
}

.attr-key {
  font-size: 11px;
  color: var(--text-muted);
  margin-bottom: 2px;
}

.attr-val {
  font-size: 12px;
  color: var(--text-primary);
  word-break: break-all;
}

.event-item {
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}

.event-name {
  font-size: 12px;
  font-weight: 600;
  color: var(--accent-orange);
  margin-bottom: 4px;
}

.log-row {
  display: flex;
  gap: 6px;
  padding: 4px 0;
  border-bottom: 1px solid var(--border);
  font-size: 11px;
}

.log-source {
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 10px;
  flex-shrink: 0;
}

.log-source.src-stdout {
  background: var(--accent-green-dim);
  color: var(--accent-green);
}

.log-source.src-stderr {
  background: var(--accent-red-dim);
  color: var(--accent-red);
}

.log-source.src-otel {
  background: var(--accent-blue-dim);
  color: var(--accent-blue);
}

.log-time {
  color: var(--text-muted);
  flex-shrink: 0;
  font-size: 10px;
}

.log-body {
  color: var(--text-secondary);
  word-break: break-all;
  min-width: 0;
}

.metrics-chart-area {
  padding: 4px 0;
}

.metrics-legend {
  display: flex;
  gap: 12px;
  font-size: 10px;
  color: var(--text-muted);
  margin-bottom: 4px;
}

.legend-cpu .legend-dot {
  display: inline-block;
  width: 8px;
  height: 3px;
  border-radius: 1px;
  background: var(--accent-blue);
  margin-right: 3px;
}

.legend-mem .legend-dot {
  display: inline-block;
  width: 8px;
  height: 3px;
  border-radius: 1px;
  background: var(--accent-purple);
  margin-right: 3px;
}

.metrics-svg {
  width: 100%;
  height: 80px;
  display: block;
}
</style>
