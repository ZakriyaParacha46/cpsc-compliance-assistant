"""Download 16 CFR parts from the eCFR API and parse them into documents and sections."""

from dataclasses import asdict, dataclass, field
from pathlib import Path

import httpx
from lxml import etree

API = "https://www.ecfr.gov/api/versioner/v1"
TITLE = 16

# CPSC parts in scope (PRD: Day 1 milestone).
PARTS = {
    "1107": "Testing and labeling pertaining to product certification",
    "1110": "Certificates of compliance",
    "1115": "Substantial product hazard reports",
    "1250": "Safety standard for toys",
    "1263": "Button cell or coin batteries (Reese's Law)",
    "1303": "Lead-containing paint",
    "1307": "Phthalates in children's toys and child care articles",
    "1500": "Hazardous substances (FHSA regulations)",
}

# Block-level tags whose text becomes a paragraph. Table rows are handled separately.
_BLOCK_TAGS = {"P", "FP", "HD1", "HD2", "HD3", "HED", "PSPACE", "CAPTION"}
_ACRONYMS = ["CPSC", "CPSIA", "CPSA", "FHSA", "ASTM", "ANSI", "UL", "U.S.", "FR"]


@dataclass
class Section:
    id: str  # "1263.3"
    heading: str  # "§ 1263.3 Requirements for ..."
    text: str  # paragraphs joined by "\n\n"
    url: str


@dataclass
class Document:
    id: str  # "cfr-1263"
    source_type: str  # "rule"
    cfr_part: str
    title: str
    url: str
    as_of: str
    sections: list[Section] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(el: etree._Element) -> str:
    return " ".join("".join(el.itertext()).split())


def _sentence_case(heading: str) -> str:
    s = heading.strip().rstrip(".")
    s = s[:1].upper() + s[1:].lower()
    for a in _ACRONYMS:
        s = s.replace(a.lower(), a) if f" {a.lower()} " in f" {s} " else s
    return s


def _section_text(div8: etree._Element) -> str:
    paras: list[str] = []
    for el in div8.iter():
        if not isinstance(el.tag, str):
            continue  # comments, processing instructions
        if el.tag == "TR":
            cells = [_clean(c) for c in el if c.tag in ("TD", "TH")]
            row = " | ".join(c for c in cells if c)
            if row:
                paras.append(row)
        elif el.tag in _BLOCK_TAGS and next(el.iterancestors("TR"), None) is None:
            t = _clean(el)
            if t:
                paras.append(t)
    return "\n\n".join(paras)


def parse_part(xml: bytes, part: str, as_of: str) -> Document:
    root = etree.fromstring(xml)
    div5 = root if root.tag == "DIV5" else root.find(".//DIV5")
    if div5 is None:
        raise ValueError(f"No DIV5 (part) element in XML for part {part}")
    head = _clean(div5.find("HEAD"))  # "PART 1263—SAFETY STANDARD FOR ..."
    title = _sentence_case(head.split("—", 1)[-1]) if "—" in head else PARTS.get(part, head)

    doc = Document(
        id=f"cfr-{part}",
        source_type="rule",
        cfr_part=part,
        title=title,
        url=f"https://www.ecfr.gov/current/title-{TITLE}/part-{part}",
        as_of=as_of,
    )
    for div8 in div5.iter("DIV8"):
        sec_id = div8.get("N", "").strip()
        head_el = div8.find("HEAD")
        heading = _clean(head_el) if head_el is not None else f"§ {sec_id}"
        text = _section_text(div8)
        if not sec_id or not text or "[Reserved]" in heading:
            continue
        doc.sections.append(
            Section(
                id=sec_id,
                heading=heading,
                text=text,
                url=f"https://www.ecfr.gov/current/title-{TITLE}/section-{sec_id}",
            )
        )
    return doc


def latest_date(client: httpx.Client) -> str:
    """The most recent date Title 16 is published for, e.g. '2026-09-22'."""
    titles = client.get(f"{API}/titles.json").raise_for_status().json()["titles"]
    return next(t["up_to_date_as_of"] for t in titles if t["number"] == TITLE)


def download_part(client: httpx.Client, part: str, as_of: str, dest: Path) -> Path:
    # The eCFR API requires a compressed response; httpx asks for gzip and decodes it.
    url = f"{API}/full/{as_of}/title-{TITLE}.xml"
    resp = client.get(url, params={"part": part}, timeout=60).raise_for_status()
    path = dest / f"part-{part}.xml"
    path.write_bytes(resp.content)
    return path


def make_client() -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": "cpsc-compliance-assistant/0.1 (portfolio project)"},
        follow_redirects=True,
        timeout=30,
    )
