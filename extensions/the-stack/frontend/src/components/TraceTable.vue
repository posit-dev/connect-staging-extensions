<script setup lang="ts">
import { ref, computed } from "vue";
import type { TraceGroup, Span } from "../types/traces";

const props = defineProps<{
  groups: TraceGroup[];
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  totalTraces: number;
  selectedSpan: Span | null;
  expandedSpans: Set<string>;
  isAtTop: boolean;
  bufferedCount: number;
  warnTraces: Set<string>;
  liveMode: boolean;
}>();

const emit = defineEmits<{
  "select-span": [span: Span];
  "toggle-expand": [spanId: string];
  "scroll-state": [atTop: boolean];
  "load-more": [];
}>();

const tableBody = ref<HTMLElement | null>(null);

function onScroll() {
  if (!tableBody.value) return;
  const el = tableBody.value;
  const atTop = el.scrollTop < 40;
  if (atTop !== props.isAtTop) {
    emit("scroll-state", atTop);
  }
  const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 200;
  if (atBottom && props.hasMore) {
    emit("load-more");
  }
}

function scrollToTopAndResume() {
  if (tableBody.value) tableBody.value.scrollTop = 0;
  emit("scroll-state", true);
}

function totalDescendants(span: Span): number {
  let count = span.children.length;
  for (const c of span.children) count += totalDescendants(c);
  return count;
}

function hasError(span: Span): boolean {
  if (span.statusCode === 2) return true;
  if (span.events.some((e) => e.name === "exception")) return true;
  return span.children.some(hasError);
}

function spanHasWarn(span: Span): boolean {
  return props.warnTraces.has(span.spanId);
}

function treeHasWarn(span: Span): boolean {
  if (props.warnTraces.has(span.spanId)) return true;
  return span.children.some(treeHasWarn);
}

function formatTime(ms: number): string {
  const d = new Date(ms);
  const h = d.getHours().toString().padStart(2, "0");
  const m = d.getMinutes().toString().padStart(2, "0");
  const s = d.getSeconds().toString().padStart(2, "0");
  return `${h}:${m}:${s}`;
}

function formatDuration(ms: number): string {
  if (ms < 1) return `${(ms * 1000).toFixed(0)}us`;
  if (ms < 1000) return `${ms.toFixed(0)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(2)}s`;
  return `${(ms / 60000).toFixed(1)}m`;
}

function formatDate(ms: number): string {
  const d = new Date(ms);
  const now = new Date();
  if (d.toDateString() === now.toDateString()) return "Today";
  const month = d.toLocaleString("en", { month: "short" });
  return `${month} ${d.getDate()}`;
}

function statusClass(code: number): string {
  if (code === 2) return "error";
  if (code === 1) return "ok";
  return "unset";
}

function spanStatusBadge(code: number): string {
  if (code === 2) return "ERR";
  return "";
}

function isTraceOngoing(group: TraceGroup): boolean {
  return group.spans.some((s) => s.ongoing);
}

interface FlatRow {
  type: "group-header" | "span";
  group?: TraceGroup;
  span?: Span;
  key: string;
  firstInGroup: boolean;
}

function flattenSpan(span: Span, out: FlatRow[], first: boolean) {
  out.push({ type: "span", span, key: span.spanId, firstInGroup: first });
  if (props.expandedSpans.has(span.spanId)) {
    for (const c of span.children) {
      flattenSpan(c, out, false);
    }
  }
}

const flatRows = computed<FlatRow[]>(() => {
  const rows: FlatRow[] = [];
  for (const g of props.groups) {
    flattenSpan(g.rootSpan, rows, true);
  }
  return rows;
});

const maxDuration = computed(() => {
  let max = 0;
  for (const g of props.groups) {
    for (const s of g.spans) {
      if (s.duration > max) max = s.duration;
    }
  }
  return max || 1;
});

function durationBarWidth(span: Span): number {
  return Math.max(1, (span.duration / maxDuration.value) * 100);
}
</script>

<template>
  <div class="trace-table-wrapper">
    <div class="table-header">
      <div class="col col-time">Time</div>
      <div class="col col-message">Message</div>
      <div class="col col-scope">Scope</div>
      <div class="col col-duration">Duration</div>
      <div class="tail-status">
        <span v-if="liveMode && isAtTop" class="status-live">
          <span class="live-dot" /> Live
        </span>
        <span v-else class="status-paused">Paused</span>
      </div>
    </div>

    <div
      v-if="!isAtTop && bufferedCount > 0"
      class="buffer-banner"
      @click="scrollToTopAndResume"
    >
      <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
        <path d="M8 12V4M5 7l3-3 3 3" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" />
      </svg>
      New traces available — click to scroll to top
    </div>

    <div v-if="loading && flatRows.length === 0" class="loading-state">
      Loading traces...
    </div>
    <div v-else-if="flatRows.length === 0" class="empty-state">
      No traces found for the selected time range.
    </div>

    <div ref="tableBody" class="table-body" v-else @scroll="onScroll">
      <div
        v-for="row in flatRows"
        :key="row.key"
        class="trace-row"
        :class="{
          selected: selectedSpan?.spanId === row.span?.spanId,
          ['status-' + statusClass(row.span?.statusCode ?? 0)]: true,
          'status-warn': row.span && !hasError(row.span) && spanHasWarn(row.span),
          'group-first': row.firstInGroup,
        }"
        @click="row.span && emit('select-span', row.span)"
      >
        <div class="col col-time mono">
          {{ row.span ? formatTime(row.span.startTime) : "" }}
        </div>
        <div class="col col-message">
          <span
            class="indent"
            :style="{ width: (row.span?.depth ?? 0) * 20 + 'px' }"
          />
          <button
            v-if="row.span && row.span.children.length > 0"
            class="expand-btn"
            :class="{ 'expand-error': hasError(row.span), 'expand-warn': !hasError(row.span) && treeHasWarn(row.span) }"
            @click.stop="emit('toggle-expand', row.span.spanId)"
          >
            <svg
              width="10"
              height="10"
              viewBox="0 0 10 10"
              :class="{ rotated: expandedSpans.has(row.span.spanId) }"
            >
              <path
                d="M3 2l4 3-4 3"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
                stroke-linecap="round"
                stroke-linejoin="round"
              />
            </svg>
            <span class="expand-count">{{ totalDescendants(row.span) }}</span>
          </button>
          <span v-else class="expand-spacer" />

          <span
            v-if="row.span && row.span.statusCode === 2"
            class="status-badge badge-error"
          >ERR</span>

          <span
            v-if="row.span && !hasError(row.span) && spanHasWarn(row.span)"
            class="status-badge badge-warn"
          >WARN</span>

          <span
            v-if="row.span?.ongoing"
            class="status-badge badge-ongoing"
          >ONGOING</span>

          <span class="span-name mono">{{ row.span?.name ?? "" }}</span>
        </div>
        <div class="col col-scope mono">
          {{ row.span?.scope ?? "" }}
        </div>
        <div class="col col-duration">
          <div class="duration-cell">
            <div
              class="duration-bar"
              :class="{ error: row.span?.statusCode === 2, ongoing: row.span?.ongoing }"
              :style="{ width: durationBarWidth(row.span!) + '%' }"
            />
            <span class="duration-text mono">
              {{ row.span ? formatDuration(row.span.duration) : "" }}
              <span v-if="row.span?.ongoing" class="ongoing-suffix">...</span>
            </span>
          </div>
        </div>
      </div>
      <div v-if="loadingMore" class="loading-more">Loading more traces...</div>
    </div>
  </div>
</template>

<style scoped>
.trace-table-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.table-header {
  display: grid;
  grid-template-columns: 70px 1fr 120px 160px auto;
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
  text-transform: capitalize;
}

.table-body {
  flex: 1;
  overflow-y: auto;
  background: #fff;
}

.trace-row {
  display: grid;
  grid-template-columns: 70px 1fr 120px 160px;
  padding: 2px 16px;
  cursor: pointer;
  transition: background 0.1s;
  border-bottom: 1px solid transparent;
  align-items: center;
  min-height: 26px;
}

.trace-row.group-first {
  border-top: 1px solid var(--gray-200);
}

.trace-row.group-first:first-child {
  border-top: none;
}

.trace-row:hover {
  background: var(--gray-100);
}

.trace-row.selected {
  background: var(--blue-50);
}

.trace-row.status-error {
  color: var(--red-600);
  background: var(--red-50);
}

.trace-row.status-warn {
  background: #fffdf5;
}

.mono {
  font-family: var(--font-mono);
}

.col-time {
  font-size: 12px;
  color: var(--gray-400);
}

.col-message {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  overflow: hidden;
}

.indent {
  flex-shrink: 0;
  display: inline-block;
}

.expand-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-width: 16px;
  height: 18px;
  padding: 1px 5px;
  border: none;
  border-radius: 4px;
  background: var(--blue-100);
  cursor: pointer;
  color: var(--blue-700);
  flex-shrink: 0;
  transition: all 0.15s;
}

.expand-btn:hover {
  background: var(--blue-200);
  color: var(--blue-800);
}

.expand-btn.expand-error {
  background: var(--red-100);
  color: var(--red-700);
}

.expand-btn.expand-error:hover {
  background: var(--red-300);
  color: var(--red-700);
}

.expand-btn.expand-warn {
  background: #fff3cd;
  color: #b8860b;
}

.expand-btn.expand-warn:hover {
  background: #ffe69c;
  color: #856404;
}

.expand-btn svg {
  transition: transform 0.15s;
}

.expand-btn svg.rotated {
  transform: rotate(90deg);
}

.expand-count {
  font-size: 10px;
  font-family: var(--font-mono);
  color: inherit;
}

.expand-spacer {
  display: inline-block;
  width: 16px;
  flex-shrink: 0;
}

.status-badge {
  display: inline-block;
  padding: 1px 6px;
  border-radius: 4px;
  font-size: 11px;
  font-family: var(--font-mono);
  font-weight: 600;
  flex-shrink: 0;
}

.badge-error {
  background: var(--red-100);
  color: var(--red-700);
}

.badge-warn {
  background: #fff8e1;
  color: #b8860b;
}

.badge-count {
  background: var(--blue-100);
  color: var(--blue-700);
}

.span-name {
  font-size: 13px;
  color: var(--gray-900);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-error .span-name {
  color: var(--red-600);
}

.col-scope {
  font-size: 12px;
  color: var(--gray-400);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.col-duration {
  padding-right: 8px;
}

.duration-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.duration-bar {
  height: 6px;
  background: var(--blue-200);
  border: 1px solid var(--blue-300);
  border-radius: 1px;
  min-width: 2px;
  flex-shrink: 0;
}

.duration-bar.error {
  background: var(--red-100);
  border-color: var(--red-300);
}

.duration-bar.ongoing {
  background: var(--orange-100);
  border-color: var(--orange-300);
  background-image: repeating-linear-gradient(
    -45deg,
    transparent,
    transparent 3px,
    rgba(0, 0, 0, 0.05) 3px,
    rgba(0, 0, 0, 0.05) 6px
  );
}

.badge-ongoing {
  background: var(--orange-100);
  color: var(--orange-600);
  animation: pulse-ongoing 2s infinite;
}

@keyframes pulse-ongoing {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.ongoing-suffix {
  color: var(--orange-500);
  font-weight: 600;
}

.duration-text {
  font-size: 12px;
  color: var(--gray-500);
  white-space: nowrap;
}

.loading-state,
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 48px;
  color: var(--gray-500);
  font-size: 14px;
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

.loading-more {
  text-align: center;
  padding: 12px;
  color: var(--gray-400);
  font-size: 13px;
}
</style>
