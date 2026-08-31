export interface RawSpan {
  traceId: string;
  spanId: string;
  parentSpanId: string;
  name: string;
  startTimeUnixNano: string;
  endTimeUnixNano: string;
  status: { code: number; message?: string };
  attributes: OtlpAttribute[];
  events: SpanEvent[];
}

export interface OtlpAttribute {
  key: string;
  value: { stringValue?: string; intValue?: string; doubleValue?: number; boolValue?: boolean };
}

export interface SpanEvent {
  name: string;
  timeUnixNano?: string;
  attributes: OtlpAttribute[];
}

export interface Span {
  traceId: string;
  spanId: string;
  parentSpanId: string;
  name: string;
  startTime: number;
  endTime: number;
  duration: number;
  ongoing: boolean;
  statusCode: number;
  statusMessage: string;
  attributes: Record<string, string>;
  events: SpanEvent[];
  scope: string;
  serviceName: string;
  jobKey: string;
  children: Span[];
  depth: number;
}

export interface TraceGroup {
  traceId: string;
  rootSpan: Span;
  spans: Span[];
  startTime: number;
  endTime: number;
  duration: number;
}

export interface TimePreset {
  label: string;
  value: number;
}
