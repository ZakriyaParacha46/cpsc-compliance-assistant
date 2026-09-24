"""Ingestion CLI. Run inside the api container:

python -m ingest download            # fetch 16 CFR parts from eCFR into data/raw (+ S3)
python -m ingest load --dry-run      # parse + chunk only, print what would be stored
python -m ingest load                # parse, chunk, embed with Titan, store in Postgres
python -m ingest stats               # what's in the database
python -m ingest show 1263.3         # the chunks for one section
python -m ingest search "coin battery warning label"   # quick vector search check
"""

import argparse
import sys
import time
from pathlib import Path

import boto3

from app.config import settings
from app.rag import store
from app.rag.embeddings import TitanEmbeddings, get_embeddings
from ingest import ecfr
from ingest.build import build_chunks
from ingest.chunking import estimate_tokens


def raw_dir() -> Path:
    return Path(settings.data_dir) / "raw" / "ecfr"


def cmd_download(args: argparse.Namespace) -> None:
    with ecfr.make_client() as client:
        as_of = ecfr.latest_date(client)
        dest = raw_dir() / as_of
        dest.mkdir(parents=True, exist_ok=True)
        print(f"eCFR Title 16 is up to date as of {as_of}. Saving to {dest}/")
        for part in args.parts:
            path = ecfr.download_part(client, part, as_of, dest)
            print(f"  part {part}: {path.stat().st_size / 1024:7.1f} KB  {ecfr.PARTS[part]}")
    (raw_dir() / "LATEST").write_text(as_of)

    if settings.data_bucket:
        s3 = boto3.client("s3", region_name=settings.aws_region)
        for path in sorted(dest.glob("*.xml")):
            key = f"raw/ecfr/{as_of}/{path.name}"
            s3.upload_file(str(path), settings.data_bucket, key)
        print(f"Copied raw files to s3://{settings.data_bucket}/raw/ecfr/{as_of}/")
    else:
        print("DATA_BUCKET not set: raw files kept locally only.")


def _latest() -> tuple[str, Path]:
    latest = raw_dir() / "LATEST"
    if not latest.exists():
        sys.exit("No downloaded data. Run: python -m ingest download")
    as_of = latest.read_text().strip()
    return as_of, raw_dir() / as_of


def cmd_load(args: argparse.Namespace) -> None:
    as_of, src = _latest()
    print(f"Loading 16 CFR as of {as_of} from {src}/")
    docs, all_chunks = [], []
    for part in args.parts:
        doc = ecfr.parse_part((src / f"part-{part}.xml").read_bytes(), part, as_of)
        chunks = build_chunks(doc)
        tokens = sum(estimate_tokens(c.text) for c in chunks)
        n_sec, n_chunks = len(doc.sections), len(chunks)
        print(f"  part {part}: {n_sec:3d} sections -> {n_chunks:3d} chunks  ~{tokens:>7,} tokens")
        docs.append(doc)
        all_chunks.append(chunks)
    total = sum(len(c) for c in all_chunks)
    print(f"Total: {sum(len(d.sections) for d in docs)} sections, {total} chunks")
    if args.dry_run:
        print("Dry run: nothing embedded or stored.")
        return

    store.ensure_schema()
    emb = get_embeddings()
    vs = store.vector_store(emb)
    started = time.time()
    for doc, chunks in zip(docs, all_chunks, strict=True):
        t0 = time.time()
        vectors = emb.embed_documents([c.text for c in chunks])
        removed = store.delete_chunks_for(doc.id)
        vs.add_embeddings(
            texts=[c.text for c in chunks],
            embeddings=vectors,
            metadatas=[c.metadata for c in chunks],
            ids=[c.id for c in chunks],
        )
        store.upsert_document(doc.to_dict())
        note = f" (replaced {removed})" if removed else ""
        print(
            f"  stored part {doc.cfr_part}: {len(chunks)} chunks in {time.time() - t0:.1f}s{note}"
        )
    store.ensure_vector_index()

    print(f"Done in {time.time() - started:.0f}s.")
    if isinstance(emb, TitanEmbeddings):
        print(f"Titan tokens: {emb.tokens_used:,}  cost: ${emb.cost_usd:.4f}")


def cmd_stats(_: argparse.Namespace) -> None:
    with store.connect() as conn:
        rows = conn.execute(
            """
            SELECT cmetadata->>'doc_id' AS doc, cmetadata->>'source_type' AS type,
                   count(*) AS chunks, count(DISTINCT cmetadata->>'section') AS sections,
                   round(avg(length(document))) AS avg_chars, max(vector_dims(embedding)) AS dims
            FROM langchain_pg_embedding GROUP BY 1, 2 ORDER BY 1
            """
        ).fetchall()
        docs = conn.execute("SELECT count(*), min(as_of), max(as_of) FROM documents").fetchone()
    if not rows:
        print("No chunks stored yet. Run: python -m ingest load")
        return
    print(f"{'document':<14}{'type':<10}{'sections':>9}{'chunks':>8}{'avg chars':>11}{'dims':>6}")
    for doc, typ, chunks, sections, avg_chars, dims in rows:
        print(f"{doc:<14}{typ:<10}{sections:>9}{chunks:>8}{int(avg_chars):>11}{dims:>6}")
    print(f"{'TOTAL':<24}{sum(r[3] for r in rows):>9}{sum(r[2] for r in rows):>8}")
    print(f"documents table: {docs[0]} docs, as of {docs[1]}..{docs[2]}")


def cmd_show(args: argparse.Namespace) -> None:
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT id, cmetadata, document FROM langchain_pg_embedding "
            "WHERE cmetadata->>'section' = %s ORDER BY id",
            (args.section,),
        ).fetchall()
    if not rows:
        sys.exit(f"No chunks for section {args.section}")
    for cid, meta, text in rows:
        print(f"── {cid}  chars {meta['start']}–{meta['end']}  {meta['url']}")
        print(text[: args.chars] + ("…" if len(text) > args.chars else ""))
        print()


def cmd_search(args: argparse.Namespace) -> None:
    emb = get_embeddings()
    vs = store.vector_store(emb)
    results = vs.similarity_search_with_score(args.query, k=args.k)
    print(f'Top {args.k} chunks for: "{args.query}"  (cosine distance: lower = closer)\n')
    for doc, dist in results:
        m = doc.metadata
        print(f"{dist:.3f}  {m['source_type']:<8} 16 CFR {m['section']:<10} {m['title'][:70]}")


def main() -> None:
    p = argparse.ArgumentParser(
        prog="python -m ingest",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    parts = {
        "nargs": "*",
        "default": list(ecfr.PARTS),
        "choices": list(ecfr.PARTS),
        "metavar": "PART",
        "help": "CFR parts (default: all)",
    }

    d = sub.add_parser("download", help="fetch CFR parts from eCFR")
    d.add_argument("--parts", **parts)
    d.set_defaults(fn=cmd_download)

    ld = sub.add_parser("load", help="parse, chunk, embed and store")
    ld.add_argument("--parts", **parts)
    ld.add_argument("--dry-run", action="store_true", help="parse and chunk only")
    ld.set_defaults(fn=cmd_load)

    sub.add_parser("stats", help="summary of stored chunks").set_defaults(fn=cmd_stats)

    sh = sub.add_parser("show", help="print the chunks of one section")
    sh.add_argument("section", help="e.g. 1263.3")
    sh.add_argument("--chars", type=int, default=600)
    sh.set_defaults(fn=cmd_show)

    se = sub.add_parser("search", help="vector search sanity check")
    se.add_argument("query")
    se.add_argument("-k", type=int, default=6)
    se.set_defaults(fn=cmd_search)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
