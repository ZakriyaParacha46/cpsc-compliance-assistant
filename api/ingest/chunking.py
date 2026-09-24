"""Section-aware chunking.

Each CFR section becomes one chunk. Only sections longer than ~800 tokens are split,
on paragraph (then sentence) boundaries, with ~100 tokens of overlap. Every chunk keeps
its character offsets into the section text so the UI can highlight the exact passage.
"""

import re
from dataclasses import dataclass

# Titan's tokenizer isn't public; ~4 characters per token is a close, conservative estimate
# for English regulatory text.
CHARS_PER_TOKEN = 4
MAX_TOKENS = 800
OVERLAP_TOKENS = 100

PARA_SEP = "\n\n"
_SENTENCE_END = re.compile(r"(?<=[.;:])\s+(?=[(A-Z0-9])")


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


@dataclass(frozen=True)
class Span:
    start: int
    end: int


def _units(text: str, max_chars: int) -> list[Span]:
    """Paragraph spans, with any paragraph longer than max_chars broken into sentences."""
    spans: list[Span] = []
    pos = 0
    for para in text.split(PARA_SEP):
        start, end = pos, pos + len(para)
        pos = end + len(PARA_SEP)
        if not para.strip():
            continue
        if end - start <= max_chars:
            spans.append(Span(start, end))
            continue
        s = start
        for m in _SENTENCE_END.finditer(para):
            cut = start + m.start()
            if cut - s >= max_chars // 4:  # avoid tiny fragments
                spans.append(Span(s, cut))
                s = start + m.end()
        spans.append(Span(s, end))
    # A single sentence can still be too long (tables): hard-split those.
    out: list[Span] = []
    for sp in spans:
        s = sp.start
        while sp.end - s > max_chars:
            out.append(Span(s, s + max_chars))
            s += max_chars
        out.append(Span(s, sp.end))
    return out


def chunk_section(
    text: str, max_tokens: int = MAX_TOKENS, overlap_tokens: int = OVERLAP_TOKENS
) -> list[Span]:
    """Split one section's text into chunk spans (offsets into `text`)."""
    if not text.strip():
        return []
    max_chars = max_tokens * CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return [Span(0, len(text))]

    units = _units(text, max_chars)
    chunks: list[Span] = []
    i = 0
    while i < len(units):
        j = i
        # Greedily add whole units while the chunk stays under the limit.
        while j + 1 < len(units) and units[j + 1].end - units[i].start <= max_chars:
            j += 1
        chunks.append(Span(units[i].start, units[j].end))
        if j + 1 >= len(units):
            break
        # Next chunk starts far enough back to repeat ~overlap_chars of context,
        # but always moves forward by at least one unit.
        k = j + 1
        while k - 1 > i and units[j].end - units[k - 1].start <= overlap_chars:
            k -= 1
        # Paragraphs longer than the overlap window: still repeat the last one if it's
        # not huge, so a chunk never starts without the paragraph that led into it.
        if k == j + 1 and j > i and units[j].end - units[j].start <= max_chars // 2:
            k = j
        i = k
    return chunks
