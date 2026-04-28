const params = new URLSearchParams(window.location.search);
export const contentGuid = params.get("guid") ?? "";

const url = new URL(document.baseURI);
const base = `${url.origin}${url.pathname}`.replace(/\/$/, "");

export function apiUrl(path: string): string {
  return `${base}${path}`;
}

export function withGuid(qs: URLSearchParams): URLSearchParams {
  if (contentGuid) qs.set("guid", contentGuid);
  return qs;
}
