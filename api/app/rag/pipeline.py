"""Question -> events. Independent of FastAPI, so it's tested directly with fakes.

Event order: sources, token*, done. Rate limits and input validation happen before this, in the
endpoint, so they can return ordinary HTTP errors (429, 422).
"""

import asyncio
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator, Callable
from dataclasses import asdict, dataclass
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.output_parsers import StrOutputParser

from app.config import settings
from app.limits import Limiter
from app.rag import citations
from app.rag.prompts import ANSWER_PROMPT, CLASSIFIER_PROMPT, clean_question, format_sources

log = logging.getLogger(__name__)

OFF_TOPIC_MESSAGE = (
    "I can only help with US consumer product safety (CPSC) compliance: testing, certificates, "
    "labeling, children's products and similar topics. This question looks outside that scope."
)
NOT_COVERED_MESSAGE = (
    "Not covered. The regulations, laws and CPSC guidance I have don't answer this question, "
    "so I won't guess. Try rephrasing it, or check CPSC's business guidance at cpsc.gov."
)


@dataclass
class Services:
    retriever: Any  # HybridRetriever, or anything with .search(question) -> SearchResult
    classifier_llm: BaseChatModel
    answer_llm: BaseChatModel
    limiter: Limiter
    log_query: Callable[[dict], None] = lambda record: None


def _citation(n: int, meta: dict) -> dict:
    return {
        "n": n,
        "chunk_id": f"{meta['doc_id']}:{meta['section']}:{meta.get('chunk_index', 0)}",
        "doc_id": meta["doc_id"],
        "doc_title": meta.get("part_title", ""),
        "section": meta["section"],
        "source_type": meta["source_type"],
        "title": meta["title"],
        "url": meta["url"],
        "start": meta["start"],
        "end": meta["end"],
    }


def _text(msg: AIMessage) -> str:
    if isinstance(msg.content, str):
        return msg.content
    return "".join(b.get("text", "") for b in msg.content if isinstance(b, dict))


def _pieces(text: str, words: int = 4) -> list[str]:
    """Split the checked answer into small token events (whitespace kept)."""
    parts = re.split(r"(\s+)", text)
    return ["".join(parts[i : i + words * 2]) for i in range(0, len(parts), words * 2)]


async def is_in_scope(services: Services, question: str) -> bool:
    chain = CLASSIFIER_PROMPT | services.classifier_llm | StrOutputParser()
    try:
        verdict = await chain.ainvoke({"question": clean_question(question)})
    except Exception:  # noqa: BLE001 - fail open: the relevance threshold still guards
        log.exception("scope classifier failed; treating question as in scope")
        return True
    return verdict.strip().upper().startswith("IN")


async def answer(services: Services, question: str, visitor: str, ip: str) -> AsyncIterator[dict]:
    started = time.monotonic()
    query_id = str(uuid.uuid4())
    record: dict[str, Any] = {"id": query_id, "visitor_id": visitor, "ip": ip, "question": question}

    def finish(status: str, cited: list[int], standards: list[str] | None = None) -> dict:
        record.update(status=status, latency_ms=int((time.monotonic() - started) * 1000))
        services.log_query(record)
        usage = asdict(services.limiter.usage(visitor))
        return {
            "type": "done",
            "query_id": query_id,
            "status": status,
            "cited": cited,
            "standards": standards or [],
            "usage": usage,
        }

    # Scope check and retrieval run at the same time: the classifier costs no extra latency.
    in_scope, result = await asyncio.gather(
        is_in_scope(services, question), asyncio.to_thread(services.retriever.search, question)
    )
    docs = result.docs
    record.update(
        chunk_ids=[_citation(0, d.metadata)["chunk_id"] for d in docs],
        best_distance=result.best_distance,
    )

    if not in_scope:
        yield {"type": "sources", "query_id": query_id, "citations": []}
        yield {"type": "token", "text": OFF_TOPIC_MESSAGE}
        yield finish("off_topic", [])
        return

    too_far = result.best_distance is None or result.best_distance > settings.relevance_max_distance
    if too_far or not docs:
        yield {"type": "sources", "query_id": query_id, "citations": []}
        yield {"type": "token", "text": NOT_COVERED_MESSAGE}
        yield finish("not_covered", [])
        return

    sources = [_citation(n, d.metadata) for n, d in enumerate(docs, start=1)]
    yield {"type": "sources", "query_id": query_id, "citations": sources}

    services.limiter.consume(visitor, ip)
    chain = ANSWER_PROMPT | services.answer_llm
    msg = await chain.ainvoke(
        {"sources": format_sources(docs), "question": clean_question(question)}
    )
    usage_meta = getattr(msg, "usage_metadata", None) or {}
    record.update(
        tokens_in=usage_meta.get("input_tokens"), tokens_out=usage_meta.get("output_tokens")
    )

    text = citations.normalize(_text(msg).strip())
    check = citations.check(text, len(docs))
    if not check.ok:
        log.info("answer rejected (%s); returning not covered", check.reason)
        record.update(rejected=check.reason)
        yield {"type": "token", "text": NOT_COVERED_MESSAGE}
        yield finish("not_covered", [])
        return

    for piece in _pieces(text):
        yield {"type": "token", "text": piece}
    cited_texts = [docs[n - 1].page_content for n in check.cited]
    record.update(cited=check.cited)
    yield finish("answered", check.cited, citations.standards_mentioned(cited_texts))
