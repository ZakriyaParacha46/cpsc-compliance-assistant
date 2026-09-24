import { useEffect, useRef, useState } from "react";
import { getDocument } from "../api";
import type { Citation, DocFull } from "../types";
import { SourceBadge } from "./SourceBadge";

interface Props {
  docId: string;
  citation: Citation | null;
  onClose: () => void;
}

export function DocViewer({ docId, citation, onClose }: Props) {
  const [doc, setDoc] = useState<DocFull | null>(null);
  const [error, setError] = useState<string | null>(null);
  const markRef = useRef<HTMLElement>(null);
  const topRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let live = true;
    setError(null);
    getDocument(docId)
      .then((d) => live && setDoc(d))
      .catch((e) => live && setError(String(e)));
    return () => {
      live = false;
    };
  }, [docId]);

  // Bring the cited passage into view, or go to the top when browsing a document.
  useEffect(() => {
    if (!doc || doc.id !== docId) return;
    const el = citation ? markRef.current : topRef.current;
    el?.scrollIntoView({ block: citation ? "center" : "start", behavior: "smooth" });
  }, [doc, docId, citation]);

  const ready = doc && doc.id === docId;
  const link = citation?.url ?? doc?.url;

  return (
    <div className="flex h-full flex-col bg-surface">
      <header className="flex items-start gap-3 border-b border-line px-5 py-4">
        <div className="flex min-w-0 flex-1 flex-col gap-1.5">
          {ready && (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <SourceBadge type={doc.source_type} />
                {doc.cfr_part && (
                  <span className="font-mono text-xs text-muted">16 CFR Part {doc.cfr_part}</span>
                )}
                <span className="font-mono text-xs text-muted">as of {doc.as_of}</span>
              </div>
              <h2 className="font-serif text-lg font-semibold leading-tight text-balance">{doc.title}</h2>
              {link && (
                <a href={link} target="_blank" rel="noreferrer" className="text-sm text-accent hover:underline">
                  {citation && doc.source_type === "rule" ? `Open § ${citation.section}` : "Open"} on{" "}
                  {{ rule: "eCFR", law: "govinfo.gov", guidance: "cpsc.gov" }[doc.source_type]} ↗
                </a>
              )}
            </>
          )}
        </div>
        <button
          onClick={onClose}
          aria-label="Close document"
          className="rounded p-1 text-muted hover:bg-paper hover:text-ink focus-visible:outline-2 focus-visible:outline-accent"
        >
          <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">
            <path d="M4 4l10 10M14 4L4 14" stroke="currentColor" strokeWidth="1.6" fill="none" />
          </svg>
        </button>
      </header>

      <div className="flex-1 overflow-y-auto px-5 py-5">
        <div ref={topRef} />
        {error && <p className="text-sm text-warn">Couldn't load this document. {error}</p>}
        {!ready && !error && <p className="text-sm text-muted">Loading…</p>}
        {ready && doc.note && (
          <p className="rounded-md bg-warn-soft px-3 py-2 text-sm text-ink">{doc.note}</p>
        )}
        {ready && (
          <div className="flex flex-col gap-7">
            {doc.sections.map((s) => {
              const hit = citation && citation.doc_id === doc.id && citation.section === s.id ? citation : null;
              return (
                <article key={s.id} className="flex flex-col gap-2">
                  <h3 className="font-serif text-[15px] font-semibold leading-snug">{s.heading}</h3>
                  <div className="whitespace-pre-line text-[14px] leading-relaxed text-ink/90">
                    {hit ? (
                      <>
                        {s.text.slice(0, hit.start)}
                        <mark ref={markRef}>{s.text.slice(hit.start, hit.end)}</mark>
                        {s.text.slice(hit.end)}
                      </>
                    ) : (
                      s.text
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
