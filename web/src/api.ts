// Thin typed fetch client + SSE subscription for the Mark API.

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const resp = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!resp.ok) {
    let detail = resp.statusText;
    try {
      const body = await resp.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new ApiError(resp.status, detail);
  }
  return resp.json();
}

export const api = {
  get: <T>(path: string) => req<T>(path),
  post: <T>(path: string, body?: unknown) =>
    req<T>(path, { method: "POST", body: body ? JSON.stringify(body) : undefined }),
  patch: <T>(path: string, body: unknown) =>
    req<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
  del: <T>(path: string) => req<T>(path, { method: "DELETE" }),
};

// Clip/caption editor (EDL) helpers.
import type { Edl, EditData, SfxItem } from "./types";

export const editor = {
  load: (id: number | string) => api.get<EditData>(`/api/edit/${id}`),
  save: (id: number | string, edl: Edl) =>
    api.post<{ ok: boolean; edl_path: string }>(`/api/edit/${id}`, edl),
  proxy: (id: number | string) =>
    api.post<{ job_id: string }>(`/api/edit/${id}/proxy`),
  render: (id: number | string) =>
    api.post<{ job_id: string }>(`/api/edit/${id}/render`),
  sfx: () => api.get<SfxItem[]>("/api/sfx"),
  job: (jobId: string) => api.get<{ status: string; progress: number; message: string; result: unknown; error: string | null }>(`/api/jobs/${jobId}`),
};

export type MarkEvent = { kind: string; ts: string; [k: string]: unknown };

/** Subscribe to the server event stream. Returns an unsubscribe function. */
export function subscribeEvents(onEvent: (e: MarkEvent) => void): () => void {
  const es = new EventSource("/api/events");
  es.onmessage = (msg) => {
    try {
      onEvent(JSON.parse(msg.data));
    } catch {
      /* ignore malformed */
    }
  };
  return () => es.close();
}
