import pytest

from ingest.build import build_chunks
from ingest.cpsc_guidance import doc_id_for, load_folder, parse_page

# Trimmed to the structure of real saved cpsc.gov pages: canonical link, h1 title,
# <article> body, an FAQ accordion, and a trailing contact box.
PAGE = b"""<!DOCTYPE html><html><head>
<title>Toy Safety | CPSC.gov</title>
<link rel="canonical" href="https://www.cpsc.gov/FAQ/Toy-Safety">
<script>var x = 1;</script>
</head><body>
<nav><ul><li>Recalls</li><li>Business</li></ul></nav>
<h1 class="page-title"><span property="dc:title">Toy Safety</span></h1>
<main id="main-content"><article>
  <span property="dc:title" content="Toy Safety" class="hidden"></span>
  <div class="padding-y-1"><p>Toys for children 12 and under need a CPC.</p></div>
  <div class="faq-accordion usa-accordion">
    <h4 class="usa-accordion__heading" id="q1">
      <button class="usa-accordion__button">What is the toy safety standard?</button></h4>
    <div class="usa-accordion__content usa-prose">
      <p>It is ASTM F963, incorporated by <a href="#">16 C.F.R. part 1250</a>.</p>
      <ul><li>Effective April 20, 2024.</li><li>Applies to toys<br>made after that date.</li></ul>
    </div>
    <h4 class="usa-accordion__heading">
      <button class="usa-accordion__button">Do toys need tracking labels?</button></h4>
    <div class="usa-accordion__content usa-prose"><p>Yes.</p></div>
  </div>
  <h2>Contact</h2><p>Use the SBO contact form.</p>
</article></main>
<footer><p>CPSC, Bethesda MD</p></footer>
</body></html>"""


def test_page_metadata_comes_from_canonical_link_and_title():
    doc = parse_page(PAGE, "2026-09-24")
    assert doc.id == "cpsc-faq-toy-safety"
    assert doc.source_type == "guidance"
    assert doc.cfr_part is None
    assert doc.title == "Toy Safety"
    assert doc.url == "https://www.cpsc.gov/FAQ/Toy-Safety"


def test_each_faq_question_is_a_section_and_menus_are_ignored():
    doc = parse_page(PAGE, "2026-09-24")
    headings = [s.heading for s in doc.sections]
    assert headings == [
        "Toy Safety",
        "What is the toy safety standard?",
        "Do toys need tracking labels?",
    ]
    text = " ".join(s.text for s in doc.sections)
    for noise in ("Recalls", "Bethesda", "var x", "SBO contact form"):
        assert noise not in text


def test_text_keeps_paragraphs_lists_and_spacing():
    s = parse_page(PAGE, "2026-09-24").sections[1]
    assert s.text.split("\n\n") == [
        "It is ASTM F963, incorporated by 16 C.F.R. part 1250.",
        "Effective April 20, 2024.",
        "Applies to toys made after that date.",
    ]
    assert s.url == "https://www.cpsc.gov/FAQ/Toy-Safety#q1"
    assert s.id == "cpsc-faq-toy-safety#2"


def test_guidance_chunks_are_labelled_non_binding():
    chunks = build_chunks(parse_page(PAGE, "2026-09-24"))
    assert chunks[1].text.startswith(
        "CPSC guidance (non-binding): Toy Safety\nWhat is the toy safety standard?"
    )
    assert chunks[0].text.startswith("CPSC guidance (non-binding): Toy Safety\n\nToys for")
    assert all(c.metadata["source_type"] == "guidance" for c in chunks)


def test_doc_id_for_urls():
    assert doc_id_for("https://www.cpsc.gov/FAQ/CPC") == "cpsc-faq-cpc"
    assert (
        doc_id_for("https://www.cpsc.gov/Business--Manufacturing/Business-Education/tracking-label")
        == "cpsc-business-education-tracking-label"
    )


def test_page_without_canonical_link_is_rejected():
    with pytest.raises(ValueError, match="canonical"):
        parse_page(b"<html><body><article><p>x</p></article></body></html>", "2026-09-24")


def test_load_folder_needs_as_of_and_rejects_duplicates(tmp_path):
    (tmp_path / "a.html").write_bytes(PAGE)
    with pytest.raises(FileNotFoundError):
        load_folder(tmp_path)
    (tmp_path / "AS_OF").write_text("2026-09-24\n")
    assert [d.as_of for d in load_folder(tmp_path)] == ["2026-09-24"]
    (tmp_path / "b.html").write_bytes(PAGE)
    with pytest.raises(ValueError, match="saved twice"):
        load_folder(tmp_path)
