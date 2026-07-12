# Knowledge Base Index — MAFD

The Coordinator's `kb_retrieve` tool answers from a small SOP knowledge base. This
file documents what's in it and how it's built. Authoritative system design:
`docs/System_Architecture.md`.

## SOP library (`data/sop/`)

Each SOP is a `.md` file with a plain `KEY: value` header (parsed until the first
blank line) followed by the body. Required header keys are **`ID`** and **`TITLE`**;
`SECTION` and `URL` are optional. Files missing `ID`/`TITLE` or with an empty body
are skipped (see `app/rag/kb_loader.py`).

| File | ID | Title |
| ---- | -- | ----- |
| `SOP-OVLD-001_feeder_overload_thermal_protection.md` | `SOP-OVLD-001` | Feeder Overload and Thermal Protection |
| `SOP-MISC-002_feeder_relay_miscoordination.md` | `SOP-MISC-002` | Feeder Relay Miscoordination Investigation |
| `SOP-THFT-003_suspected_theft_related_overload.md` | `SOP-THFT-003` | Suspected Theft-Related Overload on Distribution Feeders |
| `SOP-TRF-004_transformer_overcurrent_protection.md` | `SOP-TRF-004` | Transformer Overcurrent and Thermal Protection |

## Header format (example)

```
ID: SOP-OVLD-001
TITLE: Feeder Overload and Thermal Protection
SECTION: 3.1 Overload Trip Criteria
URL: https://internal.example/sops/feeder_overload_thermal_protection

This SOP describes how to identify and respond to overload conditions ...
```

The header keys map onto the citation metadata the Coordinator returns
(`source_id` ← `ID`, `title` ← `TITLE`, `section` ← `SECTION`, `url` ← `URL`).

## Vector store

- **Embeddings:** local `BAAI/bge-small-en-v1.5` (384-dim), CPU, offline — no API
  key, no per-call cost (`app/rag/config.py`, `app/rag/vector_store.py`).
- **Store:** Chroma, persisted to `artifacts/kb/` (collection `mafd_sop_kb`).
- **Build/refresh:** `scripts/refresh_kb.py`, or `get_vectordb(force_rebuild=True)`.
  The Docker entrypoint builds it once at container start; the running app then
  **loads** the persisted store rather than rebuilding it.
- **Changing the embedding model changes the vector dimensionality → the store must
  be rebuilt** (`force_rebuild=True`).

## Retrieval

`kb_retrieve(query, k=3)` runs a similarity search and returns a list of
`{source_id, title, section, url, snippet}`. It **degrades gracefully**: if the
store is unavailable it logs and returns `[]`, so a KB hiccup never crashes a
diagnosis — the ticket is produced without citations.
