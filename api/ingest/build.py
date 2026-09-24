"""Turn a parsed Document into chunks ready to embed: text, stable id, and metadata."""

from dataclasses import dataclass
from typing import Any

from ingest.chunking import chunk_section
from ingest.ecfr import Document


@dataclass(frozen=True)
class Chunk:
    id: str  # stable, so re-loading upserts instead of duplicating: "cfr-1263:1263.3:0"
    text: str  # what gets embedded and shown to the model
    metadata: dict[str, Any]


def build_chunks(doc: Document) -> list[Chunk]:
    chunks: list[Chunk] = []
    for sec in doc.sections:
        spans = chunk_section(sec.text)
        for i, span in enumerate(spans):
            body = sec.text[span.start : span.end]
            # A short header gives each chunk its context: which rule or page, which section.
            # It helps both the embedding and the model's citations.
            if doc.source_type == "rule":
                header = f"16 CFR {sec.heading}\nPart {doc.cfr_part}: {doc.title}"
            elif doc.source_type == "law":
                header = f"{sec.heading}\n{doc.title} (statute)"
            elif sec.heading == doc.title:
                header = f"CPSC guidance (non-binding): {doc.title}"
            else:
                header = f"CPSC guidance (non-binding): {doc.title}\n{sec.heading}"
            chunks.append(
                Chunk(
                    id=f"{doc.id}:{sec.id}:{i}",
                    text=f"{header}\n\n{body}",
                    metadata={
                        "doc_id": doc.id,
                        "source_type": doc.source_type,
                        "cfr_part": doc.cfr_part,
                        "section": sec.id,
                        "title": sec.heading,
                        "part_title": doc.title,
                        "url": sec.url,
                        "as_of": doc.as_of,
                        "chunk_index": i,
                        "chunk_count": len(spans),
                        # Offsets into the section text, for the viewer's highlight.
                        "start": span.start,
                        "end": span.end,
                    },
                )
            )
    return chunks
