"""Endpoints and limiter against a real Postgres + pgvector (CI service container).
Skipped when no database is reachable. Models are fake: no AWS."""

import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.limits import Limiter, PostgresStore
from app.rag import store
from app.rag.embeddings import get_embeddings
from ingest.build import build_chunks
from ingest.ecfr import parse_part
from tests.test_api import RecordingChat, StubRetriever
from tests.test_ecfr_parse import XML
from tests.test_store_integration import _db_up

pytestmark = pytest.mark.skipif(not _db_up(), reason="no Postgres available")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "llm_mode", "fake")
    monkeypatch.setattr(settings, "collection_name", "pytest-api")
    store.ensure_app_schema()
    doc = parse_part(XML, "9999", "2026-09-22")
    chunks = build_chunks(doc)
    emb = get_embeddings()
    store.vector_store(emb).add_embeddings(
        texts=[c.text for c in chunks],
        embeddings=emb.embed_documents([c.text for c in chunks]),
        metadatas=[c.metadata for c in chunks],
        ids=[c.id for c in chunks],
    )
    store.upsert_document(doc.to_dict())
    services = main.Services(
        retriever=StubRetriever(),
        classifier_llm=RecordingChat(responses=["IN"]),
        answer_llm=RecordingChat(responses=["Importers certify [1]."]),
        limiter=Limiter(PostgresStore(settings.database_url)),
        log_query=store.insert_query_log,
    )
    yield TestClient(main.create_app(services))
    store.delete_chunks_for(doc.id)
    with store.connect() as conn:
        conn.execute("DELETE FROM documents WHERE id = %s", (doc.id,))


def test_documents_list_and_detail(client):
    docs = client.get("/api/documents").json()
    mine = next(d for d in docs if d["id"] == "cfr-9999")
    assert mine["section_count"] == 2 and mine["source_type"] == "rule"
    full = client.get("/api/documents/cfr-9999").json()
    assert [s["id"] for s in full["sections"]] == ["9999.1", "9999.2"]
    assert client.get("/api/documents/nope").status_code == 404


def test_source_by_chunk_id(client):
    chunk = client.get("/api/sources/cfr-9999:9999.1:0").json()
    assert chunk["metadata"]["section"] == "9999.1"
    assert "widgets" in chunk["text"]


def test_ask_is_logged_and_feedback_stored(client):
    resp = client.post("/api/ask", json={"question": "Who certifies widgets?"})
    query_id = resp.text.split('"query_id": "')[1].split('"')[0]
    with store.connect() as conn:
        status, cited = conn.execute(
            "SELECT status, cited FROM query_log WHERE id = %s", (query_id,)
        ).fetchone()
    assert (status, cited) == ("answered", [1])
    assert client.post("/api/feedback", json={"query_id": query_id, "rating": 1}).status_code == 204
    bad = client.post("/api/feedback", json={"query_id": query_id, "rating": 5})
    assert bad.status_code == 422


def test_postgres_counter_is_atomic_per_key_and_day():
    s = PostgresStore(settings.database_url)
    key = f"test:{uuid.uuid4()}"
    day = date(2026, 9, 24)
    assert [s.incr(key, day) for _ in range(3)] == [1, 2, 3]
    assert s.get(key, day) == 3
    assert s.get(key, date(2026, 9, 25)) == 0
