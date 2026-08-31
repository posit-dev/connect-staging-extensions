<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from "vue";
import type { TraceGroup } from "../types/traces";

const props = defineProps<{
  groups: TraceGroup[];
  timeRange: { from: string; to: string };
}>();

const emit = defineEmits<{
  customRange: [range: { from: string; to: string }];
}>();

const BUCKET_COUNT = 80;

const chartEl = ref<HTMLElement | null>(null);
const isDragging = ref(false);
const dragStartX = ref(0);
const dragCurrentX = ref(0);

function xToTime(x: number): number {
  if (!chartEl.value) return 0;
  const rect = chartEl.value.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
  const from = new Date(props.timeRange.from).getTime();
  const to = new Date(props.timeRange.to).getTime();
  return from + ratio * (to - from);
}

function selectionStyle() {
  if (!chartEl.value || !isDragging.value) return { display: "none" };
  const rect = chartEl.value.getBoundingClientRect();
  const left = Math.min(dragStartX.value, dragCurrentX.value) - rect.left;
  const right = Math.max(dragStartX.value, dragCurrentX.value) - rect.left;
  const width = right - left;
  if (width < 2) return { display: "none" };
  return {
    left: left + "px",
    width: width + "px",
  };
}

function onMouseDown(e: MouseEvent) {
  if (e.button !== 0) return;
  isDragging.value = true;
  dragStartX.value = e.clientX;
  dragCurrentX.value = e.clientX;
}

function onMouseMove(e: MouseEvent) {
  if (!isDragging.value) return;
  dragCurrentX.value = e.clientX;
}

function onMouseUp(e: MouseEvent) {
  if (!isDragging.value) return;
  isDragging.value = false;
  const startT = xToTime(dragStartX.value);
  const endT = xToTime(e.clientX);
  const from = Math.min(startT, endT);
  const to = Math.max(startT, endT);
  if (to - from < 1000) return;
  emit("customRange", {
    from: new Date(from).toISOString(),
    to: new Date(to).toISOString(),
  });
}

onMounted(() => {
  document.addEventListener("mousemove", onMouseMove);
  document.addEventListener("mouseup", onMouseUp);
});

onUnmounted(() => {
  document.removeEventListener("mousemove", onMouseMove);
  document.removeEventListener("mouseup", onMouseUp);
});

interface Bucket {
  key: number;
  count: number;
  errorCount: number;
  height: number;
  errorHeight: number;
}

const buckets = computed<Bucket[]>(() => {
  const from = new Date(props.timeRange.from).getTime();
  const to = new Date(props.timeRange.to).getTime();
  const range = to - from;
  if (range <= 0) return [];

  const bucketWidth = range / BUCKET_COUNT;
  const step = snapStep(bucketWidth);
  const alignedFrom = Math.floor(from / step) * step;

  const slotCount = Math.ceil((to - alignedFrom) / step) + 1;
  const counts = new Array(slotCount).fill(0);
  const errors = new Array(slotCount).fill(0);

  for (const g of props.groups) {
    const idx = Math.floor((g.startTime - alignedFrom) / step);
    if (idx >= 0 && idx < slotCount) {
      counts[idx]++;
      if (g.rootSpan.statusCode === 2) errors[idx]++;
    }
  }

  const visible: { key: number; count: number; errorCount: number }[] = [];
  for (let i = 0; i < slotCount; i++) {
    const edgeMs = alignedFrom + i * step;
    if (edgeMs + step <= from) continue;
    if (edgeMs >= to) break;
    visible.push({ key: edgeMs, count: counts[i], errorCount: errors[i] });
  }

  while (visible.length > BUCKET_COUNT) visible.shift();

  const maxCount = Math.max(1, ...visible.map((b) => b.count));
  return visible.map((b) => ({
    key: b.key,
    count: b.count,
    errorCount: b.errorCount,
    height: (b.count / maxCount) * 100,
    errorHeight: (b.errorCount / maxCount) * 100,
  }));
});

function snapStep(raw: number): number {
  const candidates = [
    1000, 2000, 5000, 10000, 15000, 30000,
    60000, 120000, 300000, 600000, 900000, 1800000,
    3600000, 7200000, 14400000, 43200000, 86400000,
  ];
  for (const c of candidates) {
    if (c >= raw * 0.8) return c;
  }
  return candidates[candidates.length - 1];
}

const timeLabels = computed(() => {
  const from = new Date(props.timeRange.from).getTime();
  const to = new Date(props.timeRange.to).getTime();
  const range = to - from;
  const labelCount = 6;
  const labels: { text: string; left: number }[] = [];

  for (let i = 0; i <= labelCount; i++) {
    const t = from + (range * i) / labelCount;
    const d = new Date(t);
    const h = d.getHours().toString().padStart(2, "0");
    const m = d.getMinutes().toString().padStart(2, "0");
    const s = d.getSeconds().toString().padStart(2, "0");
    const mon = d.toLocaleString("en", { month: "short" });
    const day = d.getDate();
    let text: string;
    if (range < 600000) text = `${h}:${m}:${s}`;
    else if (range < 86400000) text = `${h}:${m}`;
    else text = `${mon} ${day}, ${h}:${m}`;
    labels.push({ text, left: (i / labelCount) * 100 });
  }
  return labels;
});
</script>

<template>
  <div class="timeline">
    <div
      ref="chartEl"
      class="chart"
      :class="{ dragging: isDragging }"
      @mousedown="onMouseDown"
    >
      <div
        v-for="b in buckets"
        :key="b.key"
        class="bar-wrapper"
      >
        <div class="bar normal" :style="{ height: b.height + '%' }" />
        <div
          v-if="b.errorCount > 0"
          class="bar error"
          :style="{ height: b.errorHeight + '%' }"
        />
      </div>
      <div class="selection-overlay" :style="selectionStyle()" />
    </div>
    <div class="time-axis">
      <span
        v-for="l in timeLabels"
        :key="l.text"
        class="time-label"
        :style="{ left: l.left + '%' }"
      >
        {{ l.text }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.timeline {
  flex-shrink: 0;
  padding: 8px 16px 0;
  padding-bottom: 4px;
  border-bottom: 1px solid var(--gray-200);
  background: #fff;
  overflow: hidden;
}

.chart {
  display: flex;
  align-items: flex-end;
  height: 60px;
  gap: 1px;
  position: relative;
  cursor: crosshair;
  user-select: none;
}

.chart.dragging {
  cursor: col-resize;
}

.selection-overlay {
  position: absolute;
  top: 0;
  bottom: 0;
  background: rgba(68, 112, 153, 0.2);
  border-left: 1px solid var(--blue-400);
  border-right: 1px solid var(--blue-400);
  pointer-events: none;
  z-index: 10;
}

.bar-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  justify-content: flex-end;
  height: 100%;
  position: relative;
}

.bar {
  border-radius: 1px 1px 0 0;
  min-height: 0;
}

.bar.normal {
  background: var(--blue-300);
}

.bar.error {
  background: var(--red-300);
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
}

.time-axis {
  position: relative;
  height: 20px;
  margin-top: 4px;
}

.time-label {
  position: absolute;
  transform: translateX(-50%);
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--gray-400);
  white-space: nowrap;
}

.time-label:first-child {
  transform: none;
}

.time-label:last-child {
  transform: translateX(-100%);
}
</style>
