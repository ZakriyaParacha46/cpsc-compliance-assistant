import type { SourceType } from "../types";

export function SourceBadge({ type }: { type: SourceType }) {
  const rule = type === "rule";
  return (
    <span
      title={rule ? "Binding regulation" : "Non-binding CPSC guidance"}
      className={`inline-block shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${
        rule ? "bg-rule-soft text-rule" : "bg-guide-soft text-guide"
      }`}
    >
      {rule ? "Rule" : "Guidance"}
    </span>
  );
}
