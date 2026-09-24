"""Parse CPSC Business Education pages saved from a browser into documents and sections.

cpsc.gov blocks automated downloads (HTTP 403, from both home and AWS IPs), so the pages
are saved by hand ("Webpage, HTML Only") into data/cpsc-html/ and committed. CPSC content
is U.S. government work, so it's public domain.

Each page's canonical URL identifies it, so filenames don't matter. Headings split a page
into sections: an FAQ page becomes one section per question.
"""

import re
from pathlib import Path
from urllib.parse import urlparse

import lxml.html
from lxml import etree

from ingest.ecfr import Document, Section

HEADINGS = {"h2", "h3", "h4", "h5"}
BLOCKS = {"p", "li", "tr", "dt", "dd", "blockquote"}
# Link lists and contact boxes at the end of pages: no substance for answering questions.
SKIP_SECTIONS = {"contact", "additional information", "additional resources", "related links"}
_SEPARATE = HEADINGS | BLOCKS | {"br", "hr", "div", "ul", "ol", "td", "th", "button"}


def _clean(el: etree._Element) -> str:
    return " ".join("".join(el.itertext()).split())


def doc_id_for(url: str) -> str:
    """https://www.cpsc.gov/FAQ/CPC -> 'cpsc-faq-cpc'."""
    path = urlparse(url).path.strip("/").lower()
    path = path.removeprefix("business--manufacturing/")
    return "cpsc-" + re.sub(r"[^a-z0-9]+", "-", path).strip("-")


def _has_block_ancestor(el: etree._Element, stop: etree._Element) -> bool:
    for anc in el.iterancestors():
        if anc is stop:
            return False
        if anc.tag in BLOCKS or anc.tag in HEADINGS:
            return True
    return False


def parse_page(html: bytes, as_of: str) -> Document:
    root = lxml.html.fromstring(html)
    canonical = root.xpath('//link[@rel="canonical"]/@href')
    if not canonical:
        raise ValueError("No canonical URL in page; was it saved from cpsc.gov?")
    url = canonical[0]

    h1 = root.xpath('//h1//*[@property="dc:title"]') or root.xpath("//h1")
    title = _clean(h1[0]) if h1 else _clean(root.find(".//title")).split(" | ")[0]

    body = root.find(".//article")
    if body is None:
        body = root.find(".//main")
    if body is None:
        raise ValueError(f"No <article> or <main> in page {url}")
    for junk in body.xpath(".//script | .//style | .//noscript | .//*[@class='hidden']"):
        junk.drop_tree()
    # Pad block boundaries and <br> with spaces so text from adjacent elements doesn't
    # run together ("certificate<br>Describe" -> "certificate Describe").
    for el in body.iter():
        if isinstance(el.tag, str) and el.tag in _SEPARATE:
            el.tail = " " + (el.tail or "")
            if el.tag not in ("br", "hr"):
                el.text = " " + (el.text or "")

    # Walk the article in reading order, starting a new section at each heading.
    sections: list[tuple[str, str | None, list[str]]] = [(title, None, [])]
    for el in body.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag in HEADINGS:
            heading = _clean(el)
            if heading:
                anchor = el.get("id") or next(iter(el.xpath(".//@id")), None)
                sections.append((heading, anchor, []))
        elif el.tag in BLOCKS and not _has_block_ancestor(el, body):
            if el.tag == "tr":
                cells = [_clean(c) for c in el if c.tag in ("td", "th")]
                text = " | ".join(c for c in cells if c)
            else:
                text = _clean(el)
            if text:
                sections[-1][2].append(text)

    doc = Document(
        id=doc_id_for(url),
        source_type="guidance",
        cfr_part=None,
        title=title,
        url=url,
        as_of=as_of,
    )
    for n, (heading, anchor, paras) in enumerate(sections, start=1):
        if not paras or heading.strip().lower() in SKIP_SECTIONS:
            continue
        doc.sections.append(
            Section(
                id=f"{doc.id}#{n}",
                heading=heading,
                text="\n\n".join(paras),
                url=f"{url}#{anchor}" if anchor else url,
            )
        )
    return doc


def load_folder(folder: Path) -> list[Document]:
    as_of_file = folder / "AS_OF"
    if not as_of_file.exists():
        raise FileNotFoundError(f"{as_of_file} missing: write the date the pages were saved")
    as_of = as_of_file.read_text().strip()
    docs = [parse_page(p.read_bytes(), as_of) for p in sorted(folder.glob("*.html"))]
    ids = [d.id for d in docs]
    dupes = {i for i in ids if ids.count(i) > 1}
    if dupes:
        raise ValueError(f"Same page saved twice: {sorted(dupes)}")
    return docs
