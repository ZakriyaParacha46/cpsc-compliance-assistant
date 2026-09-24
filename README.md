# CPSC Compliance Assistant

Ask US consumer product safety (CPSC) compliance questions in plain English and get answers cited to the exact 16 CFR section or CPSC guidance page, each labelled **Rule** (binding) or **Guidance** (non-binding).

RAG on AWS: FastAPI + LangChain retrieve passages from PostgreSQL + pgvector, and Claude Haiku 4.5 on Amazon Bedrock writes the answer from them.

> Informational only, not legal advice.

## Status
Work in progress. The build log and diagrams are coming.

## Try the UI with sample data
```bash
make preview   # http://127.0.0.1:5173, real 16 CFR text, no backend or AWS needed
```
