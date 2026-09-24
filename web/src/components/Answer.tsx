import { useState } from "react";
import { sendFeedback } from "../api";
import type { AnswerStatus, Citation } from "../types";

export interface AnswerState {
  question: string;
  text: string;
  citations: Citation[]; // all retrieved sources, numbered
  cited: number[] | null; // which of them the answer cites (known when done)
  standards: string[];
  status: AnswerStatus | null; // null while streaming
  error: string | null;
  queryId: string | null;
}

function Feedback({ queryId }: { queryId: string }) {
  const [sent, setSent] = useState<1 | -1 | null>(null);
  const vote = (rating: 1 | -1) => {
    setSent(rating);
    sendFeedback(queryId, rating).catch(() => setSent(null));
  };
  if (sent) return <p className="text-xs text-muted">Thanks, feedback recorded.</p>;
  return (
    <div className="flex items-center gap-2 text-xs text-muted">
      <span>Was this answer useful?</span>
      {([1, -1] as const).map((r) => (
        <button
          key={r}
          onClick={() => vote(r)}
          aria-label={r === 1 ? "Useful" : "Not useful"}
          className="rounded border border-line px-2 py-0.5 hover:border-accent hover:text-accent focus-visible:outline-2 focus-visible:outline-accent"
        >
          {r === 1 ? "👍" : "👎"}
        </button>
      ))}
    </div>
  );
}

interface Props {
  answer: AnswerState;
  activeCitation: number | null;
  onOpenCitation: (c: Citation) => void;
}

/** Renders answer text, turning each [n] marker into a button that opens that source. */
function AnswerText({ text, citations, activeCitation, onOpenCitation }: {
  text: string;
  citations: Citation[];
  activeCitation: number | null;
  onOpenCitation: (c: Citation) => void;
}) {
  return (
    <div className="flex flex-col gap-4">
      {text.split(/\n\n+/).map((para, i) => (
        <p key={i} className="max-w-[68ch] text-[16px] leading-[1.7]">
          {para.split(/(\[\d+\])/).map((part, j) => {
            const m = /^\[(\d+)\]$/.exec(part);
            const c = m && citations.find((x) => x.n === Number(m[1]));
            if (!c) return <span key={j}>{part}</span>;
            return (
              <button
                key={j}
                onClick={() => onOpenCitation(c)}
                title={c.source_type === "rule" ? `16 CFR ${c.section}` : c.title}
                className={`mx-0.5 inline-flex -translate-y-0.5 items-center rounded px-1 font-mono text-[11px] font-medium leading-4 transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
                  activeCitation === c.n ? "bg-accent text-on-accent" : "bg-accent-soft text-accent hover:bg-accent hover:text-on-accent"
                }`}
              >
                {c.n}
              </button>
            );
          })}
        </p>
      ))}
    </div>
  );
}

export function Answer({ answer, activeCitation, onOpenCitation }: Props) {
  const streaming = answer.status === null && !answer.error;
  const box =
    answer.status === "not_covered"
      ? "border-warn/30 bg-warn-soft"
      : answer.status === "off_topic"
        ? "border-line bg-paper"
        : "border-line bg-surface";

  return (
    <div className="flex flex-col gap-4">
      <p className="font-serif text-xl font-semibold leading-snug text-balance">{answer.question}</p>

      {answer.error ? (
        <div role="alert" className="rounded-lg border border-warn/30 bg-warn-soft px-5 py-4 text-[15px]">
          {answer.error}
        </div>
      ) : (
        <div className={`rounded-lg border px-5 py-5 ${box}`} aria-live="polite" aria-busy={streaming}>
          {answer.status === "not_covered" && (
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-warn">Not covered</p>
          )}
          {answer.status === "off_topic" && (
            <p className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">Outside CPSC scope</p>
          )}
          {answer.text ? (
            <AnswerText
              text={answer.text}
              citations={answer.citations}
              activeCitation={activeCitation}
              onOpenCitation={onOpenCitation}
            />
          ) : (
            <p className="text-muted">
              {answer.citations.length
                ? `Found ${answer.citations.length} sources. Writing the answer…`
                : "Searching the regulations…"}
            </p>
          )}
          {streaming && answer.text && (
            <span className="ml-0.5 inline-block h-4 w-1.5 animate-pulse bg-accent align-middle" aria-hidden="true" />
          )}
          {answer.status === "answered" && answer.standards.length > 0 && (
            <p className="mt-4 border-t border-line pt-3 text-sm text-muted">
              <span className="font-medium text-ink">Referenced standard not included: </span>
              {answer.standards.join(", ")}. The rule incorporates this standard by reference, and its full text
              isn't in this app's sources.
            </p>
          )}
        </div>
      )}

      {answer.status === "answered" && answer.queryId && <Feedback queryId={answer.queryId} />}

      {!streaming && (
        <p className="text-xs leading-relaxed text-muted">
          Informational only, not legal advice. Check the cited regulation, or ask a compliance professional,
          before relying on this answer.
        </p>
      )}
    </div>
  );
}
