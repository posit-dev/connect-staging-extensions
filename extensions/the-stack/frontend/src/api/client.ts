import type { Span, TraceGroup, RawSpan, OtlpAttribute } from "../types/traces";
import type { LogEntry, LogsResponse } from "../types/logs";
import { withGuid, apiUrl } from "../guid";

function attrValue(attr: OtlpAttribute): string {
  const v = attr.value;
  if (v.stringValue !== undefined) return v.stringValue;
  if (v.intValue !== undefined) return v.intValue;
  if (v.doubleValue !== undefined) return String(v.doubleValue);
  if (v.boolValue !== undefined) return String(v.boolValue);
  return "";
}

function attrsToRecord(attrs: OtlpAttribute[]): Record<string, string> {
  const rec: Record<string, string> = {};
  for (const a of attrs) {
    rec[a.key] = attrValue(a);
  }
  return rec;
}

function parseSpans(rows: any[]): Span[] {
  const spans: Span[] = [];
  for (const row of rows) {
    const resourceSpans = row.resourceSpans ?? [];
    for (const rs of resourceSpans) {
      const resourceAttrs = attrsToRecord(rs.resource?.attributes ?? []);
      const serviceName = resourceAttrs["service.name"] ?? "";
      const jobKey = resourceAttrs["job.key"] ?? "";
      const scopeSpans = rs.scopeSpans ?? [];
      for (const ss of scopeSpans) {
        const scopeName = ss.scope?.name ?? "";
        const rawSpans: RawSpan[] = ss.spans ?? [];
        for (const s of rawSpans) {
          const startNano = Number(BigInt(s.startTimeUnixNano));
          const endNano = Number(BigInt(s.endTimeUnixNano));
          const ongoing = endNano === 0 || endNano <= startNano;
          const effectiveEnd = ongoing ? Date.now() * 1e6 : endNano;
          spans.push({
            traceId: s.traceId,
            spanId: s.spanId,
            parentSpanId: s.parentSpanId ?? "",
            name: s.name,
            startTime: startNano / 1e6,
            endTime: effectiveEnd / 1e6,
            duration: (effectiveEnd - startNano) / 1e6,
            ongoing,
            statusCode: s.status?.code ?? 0,
            statusMessage: s.status?.message ?? "",
            attributes: attrsToRecord(s.attributes ?? []),
            events: s.events ?? [],
            scope: scopeName,
            serviceName,
            jobKey,
            children: [],
            depth: 0,
          });
        }
      }
    }
  }
  return spans;
}

function buildTraceGroups(spans: Span[]): TraceGroup[] {
  const byTrace = new Map<string, Span[]>();
  for (const s of spans) {
    const list = byTrace.get(s.traceId) ?? [];
    list.push(s);
    byTrace.set(s.traceId, list);
  }

  const groups: TraceGroup[] = [];
  for (const [traceId, traceSpans] of byTrace) {
    const byId = new Map<string, Span>();
    for (const s of traceSpans) byId.set(s.spanId, s);

    const roots: Span[] = [];
    for (const s of traceSpans) {
      const parent = byId.get(s.parentSpanId);
      if (parent) {
        parent.children.push(s);
        s.depth = -1;
      } else {
        roots.push(s);
      }
    }

    function setDepth(span: Span, d: number) {
      span.depth = d;
      span.children.sort((a, b) => a.startTime - b.startTime);
      for (const c of span.children) setDepth(c, d + 1);
    }
    for (const r of roots) setDepth(r, 0);

    const rootSpan = roots[0] ?? traceSpans[0];
    const starts = traceSpans.map((s) => s.startTime);
    const ends = traceSpans.map((s) => s.endTime);

    groups.push({
      traceId,
      rootSpan,
      spans: traceSpans,
      startTime: Math.min(...starts),
      endTime: Math.max(...ends),
      duration: Math.max(...ends) - Math.min(...starts),
    });
  }

  groups.sort((a, b) => b.startTime - a.startTime);
  return groups;
}

export async function fetchTraceSpans(params: {
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}): Promise<{ spans: Span[]; total: number }> {
  const qs = withGuid(new URLSearchParams());
  if (params.from) qs.set("from", params.from);
  if (params.to) qs.set("to", params.to);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));

  const resp = await fetch(apiUrl(`/api/traces?${qs}`));
  const data = await resp.json();
  if (data.setup_required) throw new Error("SETUP_REQUIRED");
  const spans = parseSpans(data.rows ?? []);
  return { spans, total: data.total ?? 0 };
}

export { buildTraceGroups };

export async function fetchTraces(params: {
  from?: string;
  to?: string;
  limit?: number;
  offset?: number;
}): Promise<{ groups: TraceGroup[]; total: number }> {
  const { spans, total } = await fetchTraceSpans(params);
  const groups = buildTraceGroups(spans);
  return { groups, total };
}

export async function fetchLogs(params: {
  from?: string;
  to?: string;
  severity?: string;
  search?: string;
  limit?: number;
  offset?: number;
}): Promise<{ entries: LogEntry[]; total: number }> {
  const qs = withGuid(new URLSearchParams());
  if (params.from) qs.set("from", params.from);
  if (params.to) qs.set("to", params.to);
  if (params.severity) qs.set("severity", params.severity);
  if (params.search) qs.set("search", params.search);
  if (params.limit) qs.set("limit", String(params.limit));
  if (params.offset) qs.set("offset", String(params.offset));

  const resp = await fetch(apiUrl(`/api/logs?${qs}`));
  const data: LogsResponse = await resp.json();
  if ((data as any).setup_required) throw new Error("SETUP_REQUIRED");
  return { entries: data.entries ?? [], total: data.entries?.length ?? 0 };
}
