"""Citation checking: the last guardrail before an answer reaches the user.

The model must cite every claim as [n], where n is one of the numbered sources it was given.
Code, not the model, decides whether an answer is acceptable.
"""

import re
from dataclasses import dataclass

# The model answers with exactly this when the sources don't support an answer.
NOT_COVERED = "NOT_COVERED"

_CITE = re.compile(r"\[(\d+(?:\s*,\s*\d+)*)\]")
# Paid standards incorporated by reference: named, but their text isn't in our sources.
_STANDARD = re.compile(r"\b(ASTM\s+F\d+(?:-\d+)?|ANSI/UL\s+\d+[A-Z]?|UL\s+\d{3,4}[A-Z]?)\b")


@dataclass(frozen=True)
class CitationCheck:
    ok: bool
    cited: list[int]  # unique source numbers, in order of first use
    reason: str = ""


def normalize(text: str) -> str:
    """Rewrite grouped citations "[1, 3]" as "[1][3]" so the UI has one format to render."""
    return _CITE.sub(lambda m: "".join(f"[{n.strip()}]" for n in m[1].split(",")), text)


def check(answer: str, n_sources: int) -> CitationCheck:
    text = answer.strip()
    if not text or text.startswith(NOT_COVERED):
        return CitationCheck(ok=False, cited=[], reason="model said not covered")
    cited: list[int] = []
    for m in _CITE.finditer(text):
        for n in (int(x) for x in m[1].split(",")):
            if not 1 <= n <= n_sources:
                return CitationCheck(ok=False, cited=[], reason=f"cites [{n}], not a source")
            if n not in cited:
                cited.append(n)
    if not cited:
        return CitationCheck(ok=False, cited=[], reason="no citations")
    return CitationCheck(ok=True, cited=cited)


def standards_mentioned(texts: list[str]) -> list[str]:
    found: list[str] = []
    for t in texts:
        for m in _STANDARD.finditer(t):
            name = " ".join(m[1].split())
            if name not in found:
                found.append(name)
    return found
