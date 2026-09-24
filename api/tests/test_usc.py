from ingest.build import build_chunks
from ingest.usc import parse_chapter

# Shape of govinfo's U.S. Code chapter HTML, including a repealed section with no
# statute text, which must not swallow the section after it.
CHAPTER = """<html><body>
<!-- documentid:15_-ch47 currentthrough:20250106 -->
<h3 class="chapter-head">CHAPTER 47-CONSUMER PRODUCT SAFETY</h3>
<!-- field-start:repealedhead -->
<h3 class="section-head">&sect;2062. Repealed. Pub. L. 97-35, title XII</h3>
<!-- field-end:repealedhead -->
<!-- field-start:repealsummary --><p class="note-body">Section related to X.</p>
<!-- field-end:repealsummary -->
<!-- field-start:head -->
<h3 class="section-head">&sect;2063. Product certification and labeling</h3>
<!-- field-end:head -->
<!-- field-start:statute -->
<h4 class="subsection-head">(a) Certification accompanying product</h4>
<p class="statutory-body">(1) <cap-smallcap>General conformity
certification</cap-smallcap>.&mdash;Every manufacturer shall issue a certificate.</p>
<p class="statutory-body-1em">(A) shall certify compliance; and</p>
<!-- field-end:statute -->
<!-- field-start:sourcecredit --><p class="source-credit">(Pub. L. 92-573)</p>
<!-- field-end:sourcecredit -->
<!-- field-start:notes --><h4 class="note-head">Amendments</h4>
<p class="note-body">2008&mdash;Subsec. (a) amended.</p><!-- field-end:notes -->
</body></html>"""


def test_parses_law_metadata_and_date():
    doc = parse_chapter(CHAPTER, "47")
    assert doc.id == "usc-cpsa"
    assert doc.source_type == "law"
    assert doc.title == "Consumer Product Safety Act (CPSA), 15 U.S.C. chapter 47"
    assert doc.as_of == "2025-01-06"


def test_repealed_section_skipped_and_next_section_kept():
    doc = parse_chapter(CHAPTER, "47")
    assert [s.id for s in doc.sections] == ["15 U.S.C. 2063"]
    s = doc.sections[0]
    assert s.heading == "15 U.S.C. § 2063 Product certification and labeling"
    assert "govinfo.gov/link/uscode/15/2063" in s.url


def test_keeps_statute_text_drops_notes_and_source_credit():
    text = parse_chapter(CHAPTER, "47").sections[0].text
    assert text.split("\n\n") == [
        "(a) Certification accompanying product",
        "(1) General conformity certification.—Every manufacturer shall issue a certificate.",
        "(A) shall certify compliance; and",
    ]
    assert "Amendments" not in text and "Pub. L." not in text


def test_law_chunk_header():
    [c] = build_chunks(parse_chapter(CHAPTER, "47"))
    assert c.text.startswith(
        "15 U.S.C. § 2063 Product certification and labeling\n"
        "Consumer Product Safety Act (CPSA), 15 U.S.C. chapter 47 (statute)\n\n"
    )
    assert c.metadata["source_type"] == "law"
