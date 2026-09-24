// Sample-mode backend for `npm run dev:mock`. The documents are real 16 CFR text pulled
// from the eCFR API. The answers are pre-written and only cover the four example questions.
import type { AskEvent, Citation, DocFull, DocSummary, Usage } from "../types";
import data from "./sample-data.json";

interface Scenario {
  match: string[];
  answer: string;
  citations: Citation[];
  standards?: string[];
}

const docs = data.documents as DocFull[];
const scenarios = data.scenarios as Scenario[];
const LIMIT = 20;
let used = 6;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
const resetsAt = () => {
  const d = new Date();
  d.setUTCHours(24, 0, 0, 0);
  return d.toISOString();
};
const usage = (): Usage => ({ used, limit: LIMIT, resets_at: resetsAt() });

export async function listDocuments(): Promise<DocSummary[]> {
  await sleep(150);
  return docs.map(({ sections, note: _note, ...d }) => ({ ...d, section_count: sections.length }));
}

export async function getDocument(id: string): Promise<DocFull> {
  await sleep(120);
  const d = docs.find((x) => x.id === id);
  if (!d) throw new Error(`No document ${id}`);
  return d;
}

export async function getUsage(): Promise<Usage> {
  return usage();
}

const OFF_TOPIC = ["fda", "food", "recipe", "weather", "stock", "poem", "fcc"];

export async function ask(
  question: string,
  onEvent: (e: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const q = question.toLowerCase();
  await sleep(350);

  if (used >= LIMIT) {
    onEvent({
      type: "error",
      code: "rate_limited",
      message: "You've used all 20 questions for today. Come back tomorrow.",
    });
    return;
  }

  const query_id = crypto.randomUUID();
  const done = (status: "answered" | "not_covered" | "off_topic", cited: number[] = [], standards: string[] = []) =>
    onEvent({ type: "done", query_id, status, cited, standards, usage: usage() });

  if (OFF_TOPIC.some((w) => q.includes(w))) {
    onEvent({ type: "sources", query_id, citations: [] });
    onEvent({
      type: "token",
      text: "I can only answer questions about US consumer product safety (CPSC) rules. This question looks like it falls under another agency or topic, so I can't help with it here.",
    });
    done("off_topic");
    return;
  }

  used += 1;
  const sc = scenarios.find((s) => s.match.some((m) => q.includes(m)));
  if (!sc) {
    onEvent({ type: "sources", query_id, citations: [] });
    onEvent({
      type: "token",
      text: "Not covered. The sources I have don't support an answer to this question, so I won't guess. (In sample mode, only the four example questions have answers.)",
    });
    done("not_covered");
    return;
  }

  onEvent({ type: "sources", query_id, citations: sc.citations });
  await sleep(250);
  // Stream a few words at a time, like the real SSE token events.
  const words = sc.answer.split(/(\s+)/);
  for (let i = 0; i < words.length; i += 3) {
    if (signal?.aborted) return;
    onEvent({ type: "token", text: words.slice(i, i + 3).join("") });
    await sleep(35);
  }
  done("answered", sc.citations.map((c) => c.n), sc.standards);
}
