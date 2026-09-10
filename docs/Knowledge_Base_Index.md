# Knowledge Base Index — MAFD

The Coordinator's `kb_retrieve` tool answers from a small SOP knowledge base. This
file documents what's in it and how it's built. Authoritative system design:
`docs/System_Architecture.md`.

## SOP library (`data/sop/`)

Each SOP is a `.md` file with a plain `KEY: value` header (parsed until the first
blank line) followed by the body. Required header keys are **`ID`** and **`TITLE`**;
`SECTION` and `URL` are optional. Files missing `ID`/`TITLE` or with an empty body
are skipped (see `app/rag/kb_loader.py`).

**Operational anomalies** (Family 2 — slow, load-related):

| ID | Title |
| -- | ----- |
| `SOP-OVLD-001` | Feeder Overload and Thermal Protection |
| `SOP-MISC-002` | Feeder Relay Miscoordination Investigation |
| `SOP-THFT-003` | Suspected Theft-Related Overload on Distribution Feeders |
| `SOP-TRF-004` | Transformer Overcurrent and Thermal Protection |

**Short-circuit and series faults** (Family 1 — every `fault_type` the classifier
can emit) plus two cross-cutting procedures:

| ID | Title | Covers |
| -- | ----- | ------ |
| `SOP-SLG-005` | Single Line-to-Ground Fault Response | `SLG` |
| `SOP-LL-006` | Phase-to-Phase Fault Response | `LL` |
| `SOP-LLG-007` | Double Line-to-Ground Fault Response | `LLG` |
| `SOP-3PH-008` | Balanced Three-Phase Fault Response | `LLL`, `LLLG` |
| `SOP-OPEN-009` | Open Conductor and Single-Phasing Response | `OPEN_1PH/2PH/3PH` |
| `SOP-HIZ-010` | High-Impedance Fault Investigation | `SHORT_ZF` (impedance-limited) |
| `SOP-FLISR-011` | Fault Location, Isolation and Service Restoration | restoration, any fault |
| `SOP-REC-012` | Recloser Operation and Lockout | reclose sequence, lockout |

> **SOP-005 through SOP-012 are SYNTHETIC REFERENCES.** They were generated for
> this knowledge base from standard protection practice, and each one says so in
> its own first paragraph. They are not approved utility procedures and must go
> through the utility's document control before any operational use. The notice
> lives in the document BODY, not the header, so it travels with the retrieved
> snippet into the ticket an operator actually reads.

### Why these exist

Before them the corpus covered only operational anomalies, so an `SLG` diagnosis
retrieved whichever of overload / theft / miscoordination / transformer scored
highest — and cited it as the justification for its recommended actions. Not a
coverage gap so much as citations that actively mislead.

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

### The query matters as much as the corpus

The classifier emits terse codes (`LL`, `OPEN_1PH`). Querying with those directly
retrieves badly, and two failures were only found by testing the real query
rather than a hand-written one:

- A bare two-letter code carries almost no semantic signal, so the surrounding
  boilerplate dominated: `"LL near b684 protection ieee13"` retrieved the RELAY
  MISCOORDINATION procedure, because "protection" and "feeder" outweighed "LL".
  `FAULT_QUERY_TERMS` in `app/faults/constants.py` expands each code into its
  physical description before querying.
- The single word **"distribution"** in the query suffix was enough on its own to
  send an `LL` fault to the open-conductor procedure. The suffix is now just
  `feeder <id>`.

Related: phrase query terms **positively**. "phase-to-phase fault with no ground
path" is the correct physics, but an embedding model reads the words present, not
the ones denied — "ground path" pulled the query toward the ground-fault
documents while "no" contributed nothing.

`tests/test_kb_retrieval.py` pins one SOP per fault type so neither failure can
return silently.

### Citations are re-verified against the KB

When the Azure agent path runs, the LLM composes `kb_citations` itself, so its
`snippet` is model output — it paraphrased past the SYNTHETIC REFERENCE notice,
dropping the provenance from the one place an operator would see it, and a
model-written snippet is a fabricated quotation of a real document.
`_restore_citation_snippets` in `app/faults/service.py` therefore replaces every
snippet and title with the authoritative KB text by `source_id`, and drops any
citation whose id is not in the store.
