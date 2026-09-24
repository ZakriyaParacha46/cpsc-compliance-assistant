"""Runs against a real Postgres + pgvector (the CI service container). Skipped when none is up.

Uses fake embeddings, so no AWS is needed.
"""

import argparse

import psycopg
import pytest

from app.config import settings
from app.rag import store
from app.rag.embeddings import DIMENSIONS, get_embeddings
from ingest import __main__ as cli
from ingest.build import build_chunks
from ingest.ecfr import parse_part
from tests.test_ecfr_parse import XML


def _db_up() -> bool:
    try:
        with psycopg.connect(settings.database_url, connect_timeout=2):
            return True
    except psycopg.Error:
        return False


pytestmark = pytest.mark.skipif(not _db_up(), reason="no Postgres available")


@pytest.fixture
def loaded(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "fake")
    monkeypatch.setattr(settings, "collection_name", "pytest")
    store.ensure_schema()
    doc = parse_part(XML, "9999", "2026-09-22")
    chunks = build_chunks(doc)
    emb = get_embeddings()
    vs = store.vector_store(emb)
    store.delete_chunks_for(doc.id)
    vs.add_embeddings(
        texts=[c.text for c in chunks],
        embeddings=emb.embed_documents([c.text for c in chunks]),
        metadatas=[c.metadata for c in chunks],
        ids=[c.id for c in chunks],
    )
    store.upsert_document(doc.to_dict())
    store.ensure_vector_index()
    yield doc, chunks, vs
    store.delete_chunks_for(doc.id)
    with store.connect() as conn:
        conn.execute("DELETE FROM documents WHERE id = %s", (doc.id,))


def test_chunks_and_document_are_stored(loaded):
    doc, chunks, _ = loaded
    with store.connect() as conn:
        n, dims = conn.execute(
            "SELECT count(*), max(vector_dims(embedding)) FROM langchain_pg_embedding "
            "WHERE cmetadata->>'doc_id' = %s",
            (doc.id,),
        ).fetchone()
        sections = conn.execute(
            "SELECT sections FROM documents WHERE id = %s", (doc.id,)
        ).fetchone()[0]
    assert n == len(chunks)
    assert dims == DIMENSIONS
    assert [s["id"] for s in sections] == ["9999.1", "9999.2"]


def test_reloading_replaces_instead_of_duplicating(loaded):
    doc, chunks, vs = loaded
    removed = store.delete_chunks_for(doc.id)
    assert removed == len(chunks)
    vs.add_embeddings(
        texts=[c.text for c in chunks],
        embeddings=[[0.1] * DIMENSIONS for _ in chunks],
        metadatas=[c.metadata for c in chunks],
        ids=[c.id for c in chunks],
    )
    with store.connect() as conn:
        (n,) = conn.execute(
            "SELECT count(*) FROM langchain_pg_embedding WHERE cmetadata->>'doc_id' = %s", (doc.id,)
        ).fetchone()
    assert n == len(chunks)


def test_search_returns_chunks_with_metadata(loaded):
    _, _, vs = loaded
    results = vs.similarity_search_with_score("widgets sold to consumers", k=2)
    assert results
    meta = results[0][0].metadata
    assert {"doc_id", "section", "source_type", "start", "end", "url"} <= meta.keys()


def test_cli_stats_and_show_run(loaded, capsys):
    cli.cmd_stats(argparse.Namespace())
    cli.cmd_show(argparse.Namespace(section="9999.1", chars=200))
    out = capsys.readouterr().out
    assert "cfr-9999" in out
    assert "cfr-9999:9999.1:0" in out
