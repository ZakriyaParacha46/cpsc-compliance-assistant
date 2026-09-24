import { useEffect, useRef, useState } from "react";
import { MOCK, ask, getUsage, listDocuments } from "./api";
import { Answer, type AnswerState } from "./components/Answer";
import { DocViewer } from "./components/DocViewer";
import { Sidebar } from "./components/Sidebar";
import type { Citation, DocSummary, Usage } from "./types";

const MAX_CHARS = 500;
const EXAMPLES = [
  "Do I need a Children's Product Certificate for a kids' LED night light?",
  "Who issues the General Certificate of Conformity, me or my factory?",
  "What does Reese's Law require for a device with a coin cell battery?",
  "What documents must my suppliers give me?",
];

type Viewer = { docId: string; citation: Citation | null } | null;

export default function App() {
  const [docs, setDocs] = useState<DocSummary[]>([]);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState<AnswerState | null>(null);
  const [viewer, setViewer] = useState<Viewer>(null);
  const [libraryOpen, setLibraryOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    listDocuments().then(setDocs).catch(() => setDocs([]));
    getUsage().then(setUsage).catch(() => setUsage(null));
  }, []);

  const busy = answer !== null && answer.status === null && !answer.error;
  const left = usage ? Math.max(usage.limit - usage.used, 0) : null;

  async function submit(q: string) {
    const text = q.trim();
    if (!text || text.length > MAX_CHARS || busy) return;
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setQuestion(text);
    setViewer(null);
    setAnswer({ question: text, text: "", citations: [], standards: [], status: null, error: null });

    await ask(
      text,
      (e) => {
        setAnswer((a) => {
          if (!a) return a;
          switch (e.type) {
            case "sources":
              return { ...a, citations: e.citations, standards: e.standards ?? [] };
            case "token":
              return { ...a, text: a.text + e.text };
            case "done":
              return { ...a, status: e.status };
            case "error":
              return { ...a, error: e.message };
          }
        });
        if (e.type === "done") setUsage(e.usage);
      },
      ctrl.signal,
    ).catch((err) =>
      setAnswer((a) => a && { ...a, error: `Something went wrong reaching the server. ${String(err)}` }),
    );
  }

  const openCitation = (c: Citation) => {
    setViewer({ docId: c.doc_id, citation: c });
    setLibraryOpen(false);
  };
  const openDoc = (docId: string) => {
    setViewer({ docId, citation: null });
    setLibraryOpen(false);
  };

  const sidebar = (
    <Sidebar
      docs={docs}
      citations={answer?.citations ?? []}
      activeDocId={viewer?.docId ?? null}
      activeCitation={viewer?.citation?.n ?? null}
      onOpenCitation={openCitation}
      onOpenDoc={openDoc}
    />
  );

  return (
    <div className="flex h-full flex-col">
      {MOCK && (
        <div className="border-b border-line bg-accent-soft px-4 py-1.5 text-center text-xs text-accent">
          Sample mode: real 16 CFR text, pre-written answers for the four example questions. No backend or AWS.
        </div>
      )}

      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-3 sm:px-6">
        <button
          onClick={() => setLibraryOpen((o) => !o)}
          className="rounded-md border border-line px-2.5 py-1 text-sm lg:hidden"
          aria-expanded={libraryOpen}
          aria-controls="library-drawer"
        >
          Sources
        </button>
        <div className="flex min-w-0 flex-col">
          <h1 className="font-serif text-lg font-semibold leading-tight">CPSC Compliance Assistant</h1>
          <p className="hidden text-xs text-muted sm:block">
            Answers from 16 CFR and CPSC guidance, with every claim cited
          </p>
        </div>
        {left !== null && usage && (
          <div className="ml-auto flex items-center gap-2" title={`Resets at ${new Date(usage.resets_at).toUTCString()}`}>
            <div className="hidden h-1.5 w-20 overflow-hidden rounded-full bg-line sm:block" aria-hidden="true">
              <div className="h-full bg-accent" style={{ width: `${(left / usage.limit) * 100}%` }} />
            </div>
            <span className="text-sm tabular-nums">
              <strong className="font-semibold">{left}</strong>
              <span className="text-muted"> of {usage.limit} left today</span>
            </span>
          </div>
        )}
      </header>

      <div
        className={`grid min-h-0 flex-1 grid-cols-1 ${
          viewer ? "lg:grid-cols-[300px_minmax(0,1fr)_minmax(400px,42%)]" : "lg:grid-cols-[300px_minmax(0,1fr)]"
        }`}
      >
        {/* Library: fixed column on desktop, drawer on smaller screens */}
        <aside className="hidden min-h-0 border-r border-line bg-paper lg:block">{sidebar}</aside>
        {libraryOpen && (
          <div className="fixed inset-0 z-30 flex lg:hidden" id="library-drawer">
            <div className="h-full w-[85%] max-w-sm border-r border-line bg-paper shadow-2xl shadow-scrim">{sidebar}</div>
            <button className="flex-1 bg-scrim/60" aria-label="Close sources" onClick={() => setLibraryOpen(false)} />
          </div>
        )}

        <main className="min-h-0 overflow-y-auto">
          <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 py-8 sm:px-8">
            <form
              onSubmit={(e) => {
                e.preventDefault();
                submit(question);
              }}
              className="flex flex-col gap-3"
            >
              <label htmlFor="question" className="text-sm font-medium">
                Ask about a product, rule or certificate
              </label>
              <div className="flex flex-col gap-2 rounded-lg border border-line bg-surface p-2 focus-within:border-accent sm:flex-row sm:items-end">
                <textarea
                  id="question"
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      submit(question);
                    }
                  }}
                  rows={2}
                  maxLength={MAX_CHARS}
                  placeholder="e.g. Does a kids' backpack need third-party testing?"
                  className="min-h-[3rem] flex-1 resize-none bg-transparent px-2 py-1.5 text-[15px] placeholder:text-muted/70 focus:outline-none"
                />
                <div className="flex items-center justify-between gap-3 sm:flex-col sm:items-end">
                  <span className={`text-xs tabular-nums ${question.length > MAX_CHARS - 50 ? "text-warn" : "text-muted"}`}>
                    {question.length}/{MAX_CHARS}
                  </span>
                  <button
                    type="submit"
                    disabled={!question.trim() || busy || left === 0}
                    className="rounded-md bg-accent px-4 py-2 text-sm font-semibold text-on-accent transition-opacity hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:opacity-40"
                  >
                    {busy ? "Answering…" : "Ask"}
                  </button>
                </div>
              </div>
              <div className="flex flex-wrap gap-2">
                {EXAMPLES.map((ex) => (
                  <button
                    key={ex}
                    type="button"
                    disabled={busy}
                    onClick={() => submit(ex)}
                    className="rounded-full border border-line bg-surface px-3 py-1.5 text-left text-[13px] text-ink/85 transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
                  >
                    {ex}
                  </button>
                ))}
              </div>
            </form>

            {answer ? (
              <Answer answer={answer} activeCitation={viewer?.citation?.n ?? null} onOpenCitation={openCitation} />
            ) : (
              <div className="flex flex-col gap-3 border-t border-line pt-6 text-[15px] text-muted">
                <p className="max-w-[62ch]">
                  Ask which CPSC rules apply to your product. Every answer cites the exact 16 CFR section or CPSC
                  guidance page it relies on, labelled <span className="font-medium text-rule">Rule</span> (binding) or{" "}
                  <span className="font-medium text-guide">Guidance</span> (non-binding).
                </p>
                <p className="max-w-[62ch]">
                  Click a citation number to open the source with the passage highlighted, or browse the library on
                  the left.
                </p>
              </div>
            )}
          </div>
        </main>

        {viewer && (
          <aside className="fixed inset-0 z-40 min-h-0 border-l border-line lg:static lg:z-auto">
            <DocViewer docId={viewer.docId} citation={viewer.citation} onClose={() => setViewer(null)} />
          </aside>
        )}
      </div>
    </div>
  );
}
