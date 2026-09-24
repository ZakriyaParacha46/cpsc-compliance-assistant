from ingest.ecfr import parse_part

XML = b"""<?xml version="1.0"?>
<DIV5 N="9999" TYPE="PART">
  <HEAD>PART 9999&#x2014;SAFETY STANDARD FOR WIDGETS</HEAD>
  <AUTH><HED>Authority:</HED><PSPACE>15 U.S.C. 2056.</PSPACE></AUTH>
  <DIV8 N="9999.1" TYPE="SECTION">
    <HEAD>&#xA7; 9999.1 Scope.</HEAD>
    <P>(a) This part applies to <I>widgets</I> sold to consumers.</P>
    <P>(b) Toys are exempt.</P>
    <CITA>[88 FR 1, Jan. 1, 2023]</CITA>
  </DIV8>
  <DIV8 N="9999.2" TYPE="SECTION">
    <HEAD>&#xA7; 9999.2 Labels.</HEAD>
    <P>Letter size must follow table 1.</P>
    <TABLE><TBODY>
      <TR><TH>Area</TH><TH>Size</TH></TR>
      <TR><TD>0-2</TD><TD><P>1/16</P></TD></TR>
    </TBODY></TABLE>
    <NOTE><HED>Note:</HED><P>See also part 1500.</P></NOTE>
  </DIV8>
  <DIV8 N="9999.3" TYPE="SECTION">
    <HEAD>&#xA7; 9999.3 [Reserved]</HEAD>
  </DIV8>
</DIV5>
"""


def test_parses_part_metadata():
    doc = parse_part(XML, "9999", "2026-09-22")
    assert doc.id == "cfr-9999"
    assert doc.source_type == "rule"
    assert doc.title == "Safety standard for widgets"
    assert doc.url.endswith("/title-16/part-9999")
    assert doc.as_of == "2026-09-22"


def test_sections_keep_numbers_headings_and_paragraphs():
    doc = parse_part(XML, "9999", "2026-09-22")
    s1 = doc.sections[0]
    assert s1.id == "9999.1"
    assert s1.heading == "§ 9999.1 Scope."
    assert s1.text == "(a) This part applies to widgets sold to consumers.\n\n(b) Toys are exempt."
    assert s1.url.endswith("/section-9999.1")


def test_tables_become_rows_without_duplicate_cell_text():
    s2 = parse_part(XML, "9999", "2026-09-22").sections[1]
    paras = s2.text.split("\n\n")
    assert "Area | Size" in paras
    assert "0-2 | 1/16" in paras
    assert paras.count("1/16") == 0  # the <P> inside the cell is not repeated
    assert "See also part 1500." in paras


def test_reserved_sections_and_citations_are_skipped():
    doc = parse_part(XML, "9999", "2026-09-22")
    assert [s.id for s in doc.sections] == ["9999.1", "9999.2"]
    assert "88 FR" not in doc.sections[0].text
