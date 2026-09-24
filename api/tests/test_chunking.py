from ingest.chunking import CHARS_PER_TOKEN, chunk_section, estimate_tokens


def para(n: int, words: int) -> str:
    return " ".join(f"p{n}w{i}" for i in range(words)) + "."


def test_short_section_is_one_chunk():
    text = "(a) Scope. This part applies to toys.\n\n(b) Effective date. 2024."
    spans = chunk_section(text)
    assert len(spans) == 1
    assert (spans[0].start, spans[0].end) == (0, len(text))


def test_empty_section_has_no_chunks():
    assert chunk_section("   ") == []


def test_long_section_splits_on_paragraphs_under_limit():
    text = "\n\n".join(para(n, 120) for n in range(12))  # ~9,000 chars
    spans = chunk_section(text, max_tokens=800)
    assert len(spans) > 1
    for s in spans:
        assert s.end - s.start <= 800 * CHARS_PER_TOKEN
        # Chunks start and end on paragraph boundaries.
        assert s.start == 0 or text[s.start - 2 : s.start] == "\n\n"
        assert s.end == len(text) or text[s.end : s.end + 2] == "\n\n"


def test_chunks_cover_whole_text_with_overlap():
    text = "\n\n".join(para(n, 120) for n in range(12))
    spans = chunk_section(text, max_tokens=800, overlap_tokens=100)
    assert spans[0].start == 0
    assert spans[-1].end == len(text)
    for a, b in zip(spans, spans[1:], strict=False):
        assert b.start < a.end, "consecutive chunks should overlap"
        assert b.start > a.start, "chunking must always move forward"


def test_offsets_slice_back_to_original_text():
    text = "\n\n".join(para(n, 150) for n in range(8))
    for s in chunk_section(text, max_tokens=300):
        piece = text[s.start : s.end]
        assert piece.strip() == piece  # no leading/trailing separators
        assert piece in text


def test_giant_single_paragraph_is_hard_split():
    text = "x" * 10_000  # e.g. a table flattened to one line
    spans = chunk_section(text, max_tokens=800)
    assert all(s.end - s.start <= 800 * CHARS_PER_TOKEN for s in spans)
    assert spans[-1].end == len(text)


def test_estimate_tokens():
    assert estimate_tokens("abcd" * 100) == 100
    assert estimate_tokens("") == 1
