"""Statutes (CPSA, FHSA) from the official U.S. Code, via the govinfo API.

govinfo publishes each U.S. Code chapter as HTML in which every section's operative text is
wrapped in <!-- field-start:statute --> ... <!-- field-end:statute --> markers. We keep that
text and drop the editorial notes (amendment history, effective dates), which are long and
don't state obligations.

The CPSIA of 2008 mostly amended these two laws, so its provisions (lead limits, phthalates,
tracking labels, third-party testing) appear inside their sections.
"""

import re
from pathlib import Path

import httpx
import lxml.html

from ingest.ecfr import Document, Section

API = "https://api.govinfo.gov"
EDITION = "2024"  # latest annual edition of the U.S. Code on govinfo

LAWS = {
    "47": ("cpsa", "Consumer Product Safety Act (CPSA)"),
    "30": ("fhsa", "Federal Hazardous Substances Act (FHSA)"),
}

_HEAD = re.compile(r'<h3 class="section-head">(.*?)</h3>', re.S)
# A section can have no statute text at all (repealed ones), so only look inside its own span.
_STATUTE = re.compile(r"<!-- field-start:statute -->(.*?)<!-- field-end:statute -->", re.S)
_BLOCK = re.compile(
    r"^(statutory-body|subsection-head|paragraph-head|subparagraph-head|clause-head)"
)
_LINK_QUERY = "type=usc&year=mostrecent&link-type=html"
_GONE = ("Repealed", "Omitted", "Transferred", "Renumbered", "Reserved")


def _text(fragment: str) -> list[str]:
    """Paragraphs of statute text from one section's HTML fragment."""
    root = lxml.html.fragment_fromstring(fragment, create_parent="div")
    paras = []
    for el in root:
        if isinstance(el.tag, str) and _BLOCK.match(el.get("class", "")):
            t = " ".join(el.text_content().split())
            if t:
                paras.append(t)
    return paras


def parse_chapter(html: str, chapter: str) -> Document:
    slug, title = LAWS[chapter]
    m = re.search(r"currentthrough:(\d{4})(\d{2})(\d{2})", html)
    as_of = f"{m[1]}-{m[2]}-{m[3]}" if m else f"{EDITION}-12-31"
    doc = Document(
        id=f"usc-{slug}",
        source_type="law",
        cfr_part=None,
        title=f"{title}, 15 U.S.C. chapter {chapter}",
        url=(
            f"https://www.govinfo.gov/app/details/USCODE-{EDITION}-title15/"
            f"USCODE-{EDITION}-title15-chap{chapter}"
        ),
        as_of=as_of,
    )
    heads = list(_HEAD.finditer(html))
    for i, m in enumerate(heads):
        span = html[m.end() : heads[i + 1].start() if i + 1 < len(heads) else len(html)]
        head_el = lxml.html.fragment_fromstring(m[1], create_parent="span")
        head = " ".join(head_el.text_content().split())
        num = re.match(r"§\s*(\d+[a-z]*)", head)
        if not num or any(w in head for w in _GONE):
            continue
        paras = [p for body in _STATUTE.findall(span) for p in _text(body)]
        if not paras:
            continue
        sec = num[1]
        doc.sections.append(
            Section(
                id=f"15 U.S.C. {sec}",
                heading=f"15 U.S.C. {head.replace('§', '§ ', 1).replace('.', '', 1)}",
                text="\n\n".join(paras),
                url=f"https://www.govinfo.gov/link/uscode/15/{sec}?{_LINK_QUERY}",
            )
        )
    return doc


def download_chapter(client: httpx.Client, chapter: str, dest: Path, api_key: str) -> Path:
    granule = f"USCODE-{EDITION}-title15-chap{chapter}"
    url = f"{API}/packages/USCODE-{EDITION}-title15/granules/{granule}/htm"
    resp = client.get(url, params={"api_key": api_key}, timeout=60).raise_for_status()
    path = dest / f"title15-chap{chapter}.htm"
    path.write_bytes(resp.content)
    return path
