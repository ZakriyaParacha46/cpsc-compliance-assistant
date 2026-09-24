import { useMemo, useState } from "react";
import type { Citation, DocSummary } from "../types";
import { SourceBadge } from "./SourceBadge";

interface Props {
  docs: DocSummary[];
  citations: Citation[];
  activeDocId: string | null;
  activeCitation: number | null;
  onOpenCitation: (c: Citation) => void;
  onOpenDoc: (docId: string) => void;
}

export function Sidebar({ docs, citations, activeDocId, activeCitation, onOpenCitation, onOpenDoc }: Props) {
  const [filter, setFilter] = useState("");

  const groups = useMemo(() => {
    const f = filter.trim().toLowerCase();
    const shown = docs.filter(
      (d) => !f || d.title.toLowerCase().includes(f) || (d.cfr_part ?? "").includes(f),
    );
    return [
      { label: "Rules", items: shown.filter((d) => d.source_type === "rule") },
      { label: "Guidance", items: shown.filter((d) => d.source_type === "guidance") },
    ];
  }, [docs, filter]);

  return (
    <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
      <section aria-labelledby="cited-h">
        <h2 id="cited-h" className="mb-2 text-[11px] font-semibold uppercase tracking-wider text-muted">
          Cited in this answer
        </h2>
        {citations.length === 0 ? (
          <p className="text-sm text-muted">Ask a question and its sources appear here.</p>
        ) : (
          <ol className="flex flex-col gap-1">
            {citations.map((c) => (
              <li key={c.n}>
                <button
                  onClick={() => onOpenCitation(c)}
                  className={`flex w-full gap-2.5 rounded-md border px-2.5 py-2 text-left transition-colors focus-visible:outline-2 focus-visible:outline-accent ${
                    activeCitation === c.n
                      ? "border-accent bg-accent-soft"
                      : "border-line bg-surface hover:border-accent/50"
                  }`}
                >
                  <span className="mt-0.5 font-mono text-xs font-medium text-accent">[{c.n}]</span>
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="flex items-center gap-2">
                      <SourceBadge type={c.source_type} />
                      <span className="font-mono text-xs text-muted">16 CFR {c.section}</span>
                    </span>
                    <span className="line-clamp-2 text-[13px] leading-snug">
                      {c.title.replace(/^§\s*[\d.]+\s*/, "")}
                    </span>
                  </span>
                </button>
              </li>
            ))}
          </ol>
        )}
      </section>

      <section aria-labelledby="lib-h" className="flex flex-col gap-3">
        <div className="flex items-baseline justify-between">
          <h2 id="lib-h" className="text-[11px] font-semibold uppercase tracking-wider text-muted">
            Sources library
          </h2>
          <span className="font-mono text-xs text-muted">{docs.length} docs</span>
        </div>
        <input
          id="library-filter"
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by title or part number"
          className="w-full rounded-md border border-line bg-surface px-3 py-1.5 text-sm placeholder:text-muted/70 focus:border-accent focus:outline-none"
        />
        {groups.map(
          (g) =>
            g.items.length > 0 && (
              <div key={g.label} className="flex flex-col gap-1">
                <h3 className="text-xs font-medium text-muted">{g.label}</h3>
                <ul className="flex flex-col">
                  {g.items.map((d) => (
                    <li key={d.id}>
                      <button
                        onClick={() => onOpenDoc(d.id)}
                        className={`flex w-full flex-col rounded px-2 py-1.5 text-left text-[13px] leading-snug hover:bg-accent-soft focus-visible:outline-2 focus-visible:outline-accent ${
                          activeDocId === d.id && activeCitation === null ? "bg-accent-soft" : ""
                        }`}
                      >
                        {d.cfr_part && <span className="font-mono text-xs text-muted">Part {d.cfr_part}</span>}
                        <span>{d.title}</span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            ),
        )}
      </section>
    </div>
  );
}
