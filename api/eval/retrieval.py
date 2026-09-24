"""Retrieval eval. Run inside the api container, against the loaded database:

    python -m eval.retrieval                 # score all configurations, write a report
    python -m eval.retrieval --threshold 0.5 # try a different relevance threshold

No answer model is called: this measures only whether the right sources reach the prompt.
Cost: about 20 Titan embedding calls (well under $0.001).
"""

import argparse
import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from langchain_core.embeddings import Embeddings

from app.config import settings
from app.rag import store
from app.rag.embeddings import get_embeddings
from app.rag.retriever import HybridRetriever, KeywordIndex
from eval.golden import GOLDEN, is_binding

# name, retriever settings
CONFIGS = [
    ("vector, no dedupe (step 7)", {"mode": "vector", "one_per_section": False}),
    ("vector", {"mode": "vector"}),
    ("bm25", {"mode": "bm25"}),
    ("hybrid", {"mode": "hybrid"}),
    ("hybrid + balanced", {"mode": "hybrid", "max_guidance": 3, "max_guidance_per_page": 2}),
]
BEST = "hybrid + balanced"


class CachedEmbeddings(Embeddings):
    """Embed each question once, however many configurations use it."""

    def __init__(self, inner: Embeddings):
        self.inner, self.cache = inner, {}

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self.inner.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        if text not in self.cache:
            self.cache[text] = self.inner.embed_query(text)
        return self.cache[text]


def label(meta: dict) -> str:
    if meta["source_type"] == "rule":
        return f"16 CFR {meta['section']}"
    if meta["source_type"] == "law":
        return meta["section"]
    return meta["doc_id"].removeprefix("cpsc-")[:40]


def matches(meta: dict, expected: str) -> bool:
    return meta["section"] == expected or meta["doc_id"] == expected


@dataclass
class QuestionResult:
    q: str
    in_scope: bool
    rank: int | None  # 1-based rank of the first expected source, None if missed
    binding_hit: bool | None  # None when the question expects no binding source
    best_distance: float | None
    top: list[str]


def run_config(retriever: HybridRetriever) -> list[QuestionResult]:
    out = []
    for item in GOLDEN:
        res = retriever.search(item["q"])
        metas = [d.metadata for d in res.docs]
        expected = item["expect"] or []
        rank = next(
            (i for i, m in enumerate(metas, 1) if any(matches(m, e) for e in expected)), None
        )
        binding = [e for e in expected if is_binding(e)]
        binding_hit = any(matches(m, e) for m in metas for e in binding) if binding else None
        out.append(
            QuestionResult(
                q=item["q"],
                in_scope=item["expect"] is not None,
                rank=rank,
                binding_hit=binding_hit,
                best_distance=res.best_distance,
                top=[label(m) for m in metas],
            )
        )
    return out


def summarize(name: str, results: list[QuestionResult], threshold: float) -> dict:
    inscope = [r for r in results if r.in_scope]
    outscope = [r for r in results if not r.in_scope]
    with_binding = [r for r in inscope if r.binding_hit is not None]
    return {
        "config": name,
        "hit@6": sum(r.rank is not None for r in inscope),
        "in_scope": len(inscope),
        "binding@6": sum(bool(r.binding_hit) for r in with_binding),
        "with_binding": len(with_binding),
        "mrr": round(sum(1 / r.rank for r in inscope if r.rank) / len(inscope), 3),
        "refused": sum((r.best_distance or 1) > threshold for r in outscope),
        "out_scope": len(outscope),
        "false_refusals": sum((r.best_distance or 1) > threshold for r in inscope),
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--threshold", type=float, default=settings.relevance_max_distance)
    args = p.parse_args()

    emb = CachedEmbeddings(get_embeddings())
    vs = store.vector_store(emb)
    index = KeywordIndex(store.all_chunks())
    print(f"Index: {len(index.docs)} chunks. Threshold: best cosine distance > {args.threshold}\n")

    summaries, details = [], {}
    for name, opts in CONFIGS:
        retriever = HybridRetriever(vector_store=vs, keyword_index=index, k=6, **opts)
        results = run_config(retriever)
        details[name] = results
        summaries.append(summarize(name, results, args.threshold))

    lines = [
        "| Configuration | hit@6 | binding source @6 | MRR | off-topic refused | false refusals |",
        "|---|---|---|---|---|---|",
    ]
    for s in summaries:
        lines.append(
            f"| {s['config']} | {s['hit@6']}/{s['in_scope']} | {s['binding@6']}/{s['with_binding']}"
            f" | {s['mrr']} | {s['refused']}/{s['out_scope']} | {s['false_refusals']} |"
        )
    table = "\n".join(lines)
    print(table)

    best = details[BEST]
    print(f"\nPer question ({BEST}):")
    for r in best:
        mark = "✓" if (r.rank if r.in_scope else (r.best_distance or 1) > args.threshold) else "✗"
        where = f"rank {r.rank}" if r.rank else ("—" if r.in_scope else "off-topic")
        bind = "" if r.binding_hit is None else ("  binding ✓" if r.binding_hit else "  binding ✗")
        print(f"{mark} d={r.best_distance:.3f}  {where:<9}{bind:<12} {r.q}")
        if r.in_scope and not r.rank:
            print(f"      got: {', '.join(r.top)}")

    ins = [r.best_distance for r in best if r.in_scope and r.best_distance is not None]
    outs = [r.best_distance for r in best if not r.in_scope and r.best_distance is not None]
    print(f"\nBest distance: in-scope max {max(ins):.3f}, off-topic min {min(outs):.3f}")
    if max(ins) < min(outs):
        print(f"Separable. A threshold between them, e.g. {(max(ins) + min(outs)) / 2:.3f}, works.")
    else:
        print(
            "Not separable by distance alone: the off-topic classifier (step 10) must catch these."
        )

    out_dir = Path(settings.data_dir) / "eval"
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%d")
    (out_dir / f"retrieval-{stamp}.md").write_text(table + "\n")
    (out_dir / f"retrieval-{stamp}.json").write_text(
        json.dumps(
            {
                "threshold": args.threshold,
                "summary": summaries,
                "hybrid": [asdict(r) for r in best],
            },
            indent=1,
        )
    )
    print(f"\nSaved {out_dir}/retrieval-{stamp}.md and .json")


if __name__ == "__main__":
    main()
