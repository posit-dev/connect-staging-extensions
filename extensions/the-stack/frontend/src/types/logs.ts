export interface LogEntry {
  timestamp: string;
  severity: string;
  body: string;
  job_key: string;
  source: string;
  hostname: string;
  io_stream: string;
  process_id: number;
  trace_id: string;
  span_id: string;
}

export interface LogsResponse {
  content_guid: string;
  entries: LogEntry[];
}
