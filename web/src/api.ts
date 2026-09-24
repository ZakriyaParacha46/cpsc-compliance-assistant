import type { AskEvent, DocFull, DocSummary, Usage } from "./types";

export const MOCK = import.meta.env.VITE_MOCK === "1";
// Loaded only in sample mode, so the sample data never ships in a real build.
const mock = () => import("./mock/mockApi");

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { credentials: "same-origin" });
  if (!res.ok) throw new Error(`${path} failed: ${res.status}`);
  return res.json() as Promise<T>;
}

export const listDocuments = (): Promise<DocSummary[]> =>
  MOCK ? mock().then((m) => m.listDocuments()) : getJson("/api/documents");

export const getDocument = (id: string): Promise<DocFull> =>
  MOCK ? mock().then((m) => m.getDocument(id)) : getJson(`/api/documents/${encodeURIComponent(id)}`);

export const getUsage = (): Promise<Usage> => (MOCK ? mock().then((m) => m.getUsage()) : getJson("/api/usage"));

/** POST /api/ask and parse the SSE stream: sources, then token*, then done (or error). */
export async function ask(
  question: string,
  onEvent: (e: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  if (MOCK) return (await mock()).ask(question, onEvent, signal);

  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ question }),
    credentials: "same-origin",
    signal,
  });
  if (!res.ok || !res.body) {
    const body = await res.json().catch(() => null);
    const err = body?.error ?? { code: "upstream_error", message: `Request failed (${res.status})` };
    onEvent({ type: "error", ...err });
    return;
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      const type = /^event: (.+)$/m.exec(frame)?.[1];
      const data = /^data: (.*)$/m.exec(frame)?.[1];
      if (type && data) onEvent({ type, ...JSON.parse(data) } as AskEvent);
    }
  }
}
