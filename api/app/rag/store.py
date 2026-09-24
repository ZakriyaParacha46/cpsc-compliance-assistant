"""Database access: full documents (for the viewer) and the pgvector chunk store (for search)."""

from typing import Any

import psycopg
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_postgres import PGVector
from psycopg.types.json import Jsonb

from app.config import settings
from app.rag.embeddings import DIMENSIONS

DOCUMENTS_DDL = """
CREATE TABLE IF NOT EXISTS documents (
    id          text PRIMARY KEY,
    source_type text NOT NULL,
    cfr_part    text,
    title       text NOT NULL,
    url         text NOT NULL,
    as_of       date NOT NULL,
    sections    jsonb NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
)
"""

# Approximate-nearest-neighbour index for cosine similarity. Tiny at our size, but it's
# what keeps search fast if the corpus grows.
HNSW_INDEX = """
CREATE INDEX IF NOT EXISTS langchain_pg_embedding_hnsw
ON langchain_pg_embedding USING hnsw (embedding vector_cosine_ops)
"""


def connect() -> psycopg.Connection:
    return psycopg.connect(settings.database_url)


def sqlalchemy_url(url: str) -> str:
    """langchain-postgres uses SQLAlchemy, which needs the psycopg3 driver named in the URL."""
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def vector_store(embeddings: Embeddings) -> PGVector:
    return PGVector(
        embeddings=embeddings,
        connection=sqlalchemy_url(settings.database_url),
        collection_name=settings.collection_name,
        embedding_length=DIMENSIONS,
        use_jsonb=True,
    )


SOURCE_TYPES = ("rule", "law", "guidance")

# Re-created on every run so existing databases pick up new source types.
SOURCE_TYPE_CHECK = f"""
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_source_type_check;
ALTER TABLE documents ADD CONSTRAINT documents_source_type_check
    CHECK (source_type IN {SOURCE_TYPES!r});
"""


def ensure_schema() -> None:
    with connect() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
        conn.execute(DOCUMENTS_DDL)
        conn.execute(SOURCE_TYPE_CHECK)


def ensure_vector_index() -> None:
    with connect() as conn:
        conn.execute(HNSW_INDEX)


def upsert_document(doc: dict[str, Any]) -> None:
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO documents (id, source_type, cfr_part, title, url, as_of, sections)
            VALUES (%(id)s, %(source_type)s, %(cfr_part)s, %(title)s, %(url)s,
                    %(as_of)s, %(sections)s)
            ON CONFLICT (id) DO UPDATE SET
                source_type = EXCLUDED.source_type, cfr_part = EXCLUDED.cfr_part,
                title = EXCLUDED.title, url = EXCLUDED.url, as_of = EXCLUDED.as_of,
                sections = EXCLUDED.sections, updated_at = now()
            """,
            {**doc, "sections": Jsonb(doc["sections"])},
        )


def all_chunks() -> list[Document]:
    """Every stored chunk in the collection, for building the in-memory BM25 index."""
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT e.document, e.cmetadata
            FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON c.uuid = e.collection_id
            WHERE c.name = %s
            """,
            (settings.collection_name,),
        ).fetchall()
    return [Document(page_content=text, metadata=meta) for text, meta in rows]


def delete_chunks_for(doc_id: str) -> int:
    """Remove a document's old chunks so a re-load never leaves stale ones behind."""
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM langchain_pg_embedding WHERE cmetadata->>'doc_id' = %s", (doc_id,)
        )
        return cur.rowcount
