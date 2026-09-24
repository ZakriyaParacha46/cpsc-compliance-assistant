import re
from pathlib import Path

from langchain_core.documents import Document

from app.rag.retriever import HybridRetriever, KeywordIndex, tokenize
from eval.golden import GOLDEN, is_binding
from ingest.cpsc_guidance import load_folder


def chunk(doc_id: str, section: str, text: str, i: int = 0) -> Document:
    return Document(
        page_content=text,
        metadata={"doc_id": doc_id, "section": section, "chunk_index": i, "source_type": "rule"},
    )


CHUNKS = [
    chunk("cfr-1110", "1110.7", "Who must certify finished products. The importer must certify."),
    chunk("cfr-1110", "1110.7", "Domestic products: the manufacturer certifies.", i=1),
    chunk(
        "cfr-1263", "1263.3", "Products containing button cell or coin batteries: ANSI/UL 4200A."
    ),
    chunk("cfr-1250", "1250.2", "Each toy must comply with ASTM F963-23."),
]


class StubVectorStore:
    """Returns a fixed ranking with distances, like PGVector.similarity_search_with_score."""

    def __init__(self, ranking: list[tuple[Document, float]]):
        self.ranking = ranking

    def similarity_search_with_score(self, query: str, k: int):
        return self.ranking[:k]


def retriever(mode="hybrid", dedupe=True, k=6):
    vs = StubVectorStore([(CHUNKS[1], 0.20), (CHUNKS[0], 0.22), (CHUNKS[3], 0.60)])
    return HybridRetriever(
        vector_store=vs, keyword_index=KeywordIndex(CHUNKS), mode=mode, k=k, one_per_section=dedupe
    )


def test_tokenize_keeps_section_numbers_and_drops_stopwords():
    assert tokenize("What does 16 CFR 1263.3 say about the ASTM F963?") == [
        "16",
        "cfr",
        "1263.3",
        "say",
        "about",
        "astm",
        "f963",
    ]


def test_bm25_finds_exact_terms_vector_search_missed():
    res = retriever(mode="hybrid").search("ANSI/UL 4200A coin batteries")
    sections = [d.metadata["section"] for d in res.docs]
    assert "1263.3" in sections  # only BM25 found it; fusion keeps it


def test_one_chunk_per_section_frees_slots():
    with_dedupe = [d.metadata["section"] for d in retriever(dedupe=True).search("certify").docs]
    without = [d.metadata["section"] for d in retriever(dedupe=False).search("certify").docs]
    assert with_dedupe.count("1110.7") == 1
    assert without.count("1110.7") == 2


def test_best_distance_comes_from_vector_search_in_every_mode():
    for mode in ("vector", "bm25", "hybrid"):
        assert retriever(mode=mode).search("certify").best_distance == 0.20


def test_k_limits_results():
    assert len(retriever(k=2).search("certify importer toy").docs) == 2


def test_golden_set_is_well_formed():
    guidance_ids = {d.id for d in load_folder(Path(__file__).parents[2] / "data" / "cpsc-html")}
    in_scope = [g for g in GOLDEN if g["expect"]]
    assert len(GOLDEN) == 22 and len(in_scope) == 19
    for g in in_scope:
        for e in g["expect"]:
            if e.startswith("cpsc-"):
                assert e in guidance_ids, e
            else:
                assert re.fullmatch(r"1\d{3}\.\d+|15 U\.S\.C\. \d+[a-z]*", e), e
        assert any(is_binding(e) for e in g["expect"]) or g["expect"], g["q"]


def guide(page: str, section: str, text: str) -> Document:
    d = chunk(page, section, text)
    d.metadata["source_type"] = "guidance"
    return d


def test_guidance_caps_make_room_for_rules_and_keep_rank_order():
    g = [guide("cpsc-faq-gcc", f"cpsc-faq-gcc#{i}", f"gcc question {i}") for i in range(4)]
    g += [guide("cpsc-gcc", "cpsc-gcc#1", "gcc page")]
    rules = [CHUNKS[0], CHUNKS[2], CHUNKS[3]]
    ranked = g + rules  # guidance out-ranks every rule, as with FAQ-phrased pages
    r = HybridRetriever(
        vector_store=StubVectorStore([]),
        keyword_index=KeywordIndex([]),
        k=6,
        max_guidance=3,
        max_guidance_per_page=2,
    )
    picked = r._select(ranked)
    kinds = [d.metadata["source_type"] for d in picked]
    pages = [d.metadata["doc_id"] for d in picked if d.metadata["source_type"] == "guidance"]
    assert len(picked) == 6
    assert kinds.count("guidance") == 3  # capped: rules got the other 3 slots
    assert pages.count("cpsc-faq-gcc") == 2  # at most 2 from one page
    assert picked == sorted(picked, key=ranked.index)  # still in fused rank order


def test_caps_fall_back_to_guidance_when_no_rules_left():
    g = [guide("p", f"p#{i}", "x") for i in range(5)]
    r = HybridRetriever(
        vector_store=StubVectorStore([]), keyword_index=KeywordIndex([]), k=4, max_guidance=1
    )
    assert len(r._select(g)) == 4  # nothing else to use, so deferred guidance fills in
