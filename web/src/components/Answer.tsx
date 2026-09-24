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
  reason: string | null; // dev only: why the answer was refused
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

type CiteProps = {
  citations: Citation[];
  activeCitation: number | null;
  onOpenCitation: (c: Citation) => void;
};

const LIST_ITEM = /^\s*(?:[-*•]|\d+[.)])\s+/;

/** One line of text: **bold** spans, and [n] markers as buttons that open that source. */
function Inline({ text, ...p }: { text: string } & CiteProps) {
  return (
    <>
      {text.split(/(\*\*[^*]+\*\*|\[\d+\])/).map((part, j) => {
        if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
          return (
            <strong key={j} className="font-semibold text-ink">
              <Inline text={part.slice(2, -2)} {...p} />
            </strong>
          );
        }
        const m = /^\[(\d+)\]$/.exec(part);
        const c = m && p.citations.find((x) => x.n === Number(m[1]));
        if (!c) return <span key={j}>{part}</span>;
        return (
          <button
            key={j}
            onClick={() => p.onOpenCitation(c)}
            title={c.source_type === "rule" ? `16 CFR ${c.section}` : c.title}
            className={`mx-0.5 inline-flex -translate-y-0.5 items-center rounded px-1 font-mono text-[11px] font-medium leading-4 transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
              p.activeCitation === c.n
                ? "bg-accent text-on-accent"
                : "bg-accent-soft text-accent hover:bg-accent hover:text-on-accent"
            }`}
          >
            {c.n}
          </button>
        );
      })}
    </>
  );
}

/** Renders the answer's small Markdown subset: paragraphs, bullet or numbered lists, bold. */
function AnswerText({ text, ...p }: { text: string } & CiteProps) {
  return (
    <div className="flex max-w-[68ch] flex-col gap-4 text-[16px] leading-[1.7]">
      {text.split(/\n\n+/).map((block, i) => {
        const lines = block.split("\n").filter((l) => l.trim());
        if (lines.length && lines.every((l) => LIST_ITEM.test(l))) {
          const ordered = /^\s*\d/.test(lines[0]);
          const items = lines.map((l, j) => (
            <li key={j}>
              <Inline text={l.replace(LIST_ITEM, "")} {...p} />
            </li>
          ));
          return ordered ? (
            <ol key={i} className="list-decimal space-y-1.5 pl-6">{items}</ol>
          ) : (
            <ul key={i} className="list-disc space-y-1.5 pl-6">{items}</ul>
          );
        }
        // A stray Markdown heading becomes a bold line.
        const heading = /^#+\s+(.*)$/.exec(block.trim());
        return (
          <p key={i}>
            <Inline text={heading ? `**${heading[1]}**` : lines.join(" ")} {...p} />
          </p>
        );
      })}
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
          {answer.reason && (
            <p className="mt-3 font-mono text-[11px] text-muted">Debug (dev only): {answer.reason}</p>
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
