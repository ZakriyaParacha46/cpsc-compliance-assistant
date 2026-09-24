from ingest.build import build_chunks
from ingest.ecfr import Document, Section


def make_doc(text: str) -> Document:
    return Document(
        id="cfr-1263",
        source_type="rule",
        cfr_part="1263",
        title="Safety standard for button cell or coin batteries",
        url="https://www.ecfr.gov/current/title-16/part-1263",
        as_of="2026-09-22",
        sections=[
            Section(
                id="1263.3",
                heading="§ 1263.3 Requirements for consumer products.",
                text=text,
                url="https://www.ecfr.gov/current/title-16/section-1263.3",
            )
        ],
    )


def test_chunk_has_header_metadata_and_stable_id():
    [c] = build_chunks(make_doc("Each product shall comply with ANSI/UL 4200A."))
    assert c.id == "cfr-1263:1263.3:0"
    assert c.text.startswith("16 CFR § 1263.3 Requirements for consumer products.\nPart 1263:")
    assert c.text.endswith("Each product shall comply with ANSI/UL 4200A.")
    m = c.metadata
    assert m["source_type"] == "rule"
    assert m["section"] == "1263.3"
    assert m["url"].endswith("/section-1263.3")
    assert (m["chunk_index"], m["chunk_count"]) == (0, 1)


def test_offsets_point_back_into_section_text():
    text = "\n\n".join(f"({i}) " + "word " * 400 for i in range(6))
    doc = make_doc(text)
    chunks = build_chunks(doc)
    assert len(chunks) > 1
    for c in chunks:
        body = text[c.metadata["start"] : c.metadata["end"]]
        assert c.text.endswith(body)
    assert [c.id for c in chunks] == [f"cfr-1263:1263.3:{i}" for i in range(len(chunks))]
