import type { SourceType } from "../types";

const BADGES: Record<SourceType, { label: string; title: string; cls: string }> = {
  rule: { label: "Rule", title: "Binding regulation (16 CFR)", cls: "bg-rule-soft text-rule" },
  law: { label: "Law", title: "Binding statute (U.S. Code)", cls: "bg-rule-soft text-rule ring-1 ring-rule/40" },
  guidance: { label: "Guidance", title: "Non-binding CPSC guidance", cls: "bg-guide-soft text-guide" },
};

export function SourceBadge({ type }: { type: SourceType }) {
  const b = BADGES[type];
  return (
    <span
      title={b.title}
      className={`inline-block shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${b.cls}`}
    >
      {b.label}
    </span>
  );
}
