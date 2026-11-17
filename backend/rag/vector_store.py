import shutil
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.rag.config import settings

from .kb_loader import load_sop_documents

_vectordb: Chroma | None = None

# Local, open-source embedding model (self-hosted, no API). Configured in
# backend/rag/config.py. Changing it requires rebuilding the vector DB (dim change).
EMBEDDING_MODEL = settings.EMBEDDING_MODEL

COLLECTION_NAME = "mafd_sop_kb"

# SOP-005..012 open with an identical provenance paragraph. It must reach the
# operator (Knowledge_Base_Index.md), but it must NOT be embedded: eight of the
# twelve documents sharing ~40 words of boilerplate pulled their vectors toward
# each other, and with one vector per whole document that was enough to beat the
# right answer. Measured before this change: the miscoordination query ranked
# SOP-LL-006 at 0.5715 against SOP-MISC-002 at 0.5737 — a 0.002 margin decided by
# shared boilerplate. It is carried in metadata instead and re-attached by
# backend/rag/retriever.py.
PROVENANCE_MARKER = "SYNTHETIC REFERENCE"

# Sections are blank-line separated (Conditions / Trip Criteria / Operator
# Actions / Notes), so paragraph-first splitting lands on them naturally.
CHUNK_SIZE = 700
CHUNK_OVERLAP = 100


def _make_embeddings():
    """
    Local, open-source sentence-embedding model served via HuggingFace
    sentence-transformers.

    Runs fully offline on CPU after a one-time weight download from the
    HuggingFace Hub - no API key and no per-call cost. Replaces the previous
    OpenAI/FakeEmbeddings split (FakeEmbeddings produced random vectors, so
    local-mode retrieval was meaningless).
    """
    print(f"[vector_store] Using local HuggingFaceEmbeddings ({EMBEDDING_MODEL}).")
    return HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL,
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},  # cosine-ready (bge recommends)
    )


def _split_provenance(body: str) -> tuple[str, str]:
    """
    Separate the SYNTHETIC REFERENCE paragraph from the body it precedes.

    Returns (provenance, remaining_body). Operational SOPs 001-004 carry no
    such notice and come back as ("", body).
    """
    paragraphs = body.split("\n\n")
    kept, provenance = [], ""
    for para in paragraphs:
        if not provenance and PROVENANCE_MARKER in para:
            provenance = " ".join(para.split())
            continue
        kept.append(para)
    return provenance, "\n\n".join(kept).strip()


def _chunk_documents(docs: list[dict]) -> tuple[list[str], list[dict]]:
    """
    One vector per SECTION, not per document.

    Whole-document vectors average a 2-3 KB SOP into a single point, which
    blurs the one paragraph that actually answers a query. Each chunk is
    prefixed with "<id> - <title>" so that (a) the document's own subject is
    present in every vector, and (b) _restore_citation_snippets, which looks a
    citation up by querying its bare source_id, still finds it now that one
    document occupies several chunks.
    """
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", " "],
    )

    texts: list[str] = []
    metadatas: list[dict] = []

    for doc in docs:
        meta = doc["metadata"]
        provenance, body = _split_provenance(doc["content"])
        header = f"{meta['source_id']} - {meta['title']}"

        for index, chunk in enumerate(splitter.split_text(body)):
            texts.append(f"{header}\n\n{chunk}")
            metadatas.append({**meta, "provenance": provenance, "chunk": index})

    return texts, metadatas


def build_vectordb(
    persist_dir: str = "artifacts/kb",
    reset: bool = False,
) -> Chroma:
    """
    Build a Chroma vector store from the current SOP knowledge base.

    Args:
        persist_dir: Directory where the vector store files will be saved.
        reset: If True, the persist directory is cleared before rebuilding.

    Returns:
        Chroma: Initialized vector store.
    """
    persist_path = Path(persist_dir)

    if reset and persist_path.exists():
        print(f"[vector_store] Resetting KB at {persist_path}...")
        shutil.rmtree(persist_path, ignore_errors=True)

    persist_path.mkdir(parents=True, exist_ok=True)

    docs = load_sop_documents()

    embeddings = _make_embeddings()

    if not docs:
        print("[vector_store] No SOP documents found. Creating empty KB.")
        return Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=embeddings,
            persist_directory=str(persist_path),
        )

    texts, metadatas = _chunk_documents(docs)

    print(
        f"[vector_store] Building KB from {len(docs)} SOP document(s) -> {len(texts)} chunk(s)..."
    )

    vectordb = Chroma.from_texts(
        texts=texts,
        metadatas=metadatas,
        embedding=embeddings,
        collection_name=COLLECTION_NAME,
        persist_directory=str(persist_path),
    )

    print("[vector_store] KB build complete.")
    return vectordb


def _load_existing_vectordb(persist_dir: str) -> Chroma | None:
    """
    Load an already-persisted KB if one exists and is non-empty; else None.

    The Docker entrypoint builds the KB in a separate process, so at runtime we
    must LOAD that store — not rebuild it. Rebuilding via Chroma.from_texts against
    a populated persist dir re-adds every SOP, duplicating the collection on every
    boot. This is the load path that avoids that.
    """
    persist_path = Path(persist_dir)
    if not persist_path.exists():
        return None
    try:
        vectordb = Chroma(
            collection_name=COLLECTION_NAME,
            embedding_function=_make_embeddings(),
            persist_directory=str(persist_path),
        )
        count = vectordb._collection.count()
        if count == 0:
            return None
        print(f"[vector_store] Loaded existing KB ({count} chunks) from {persist_path}.")
        return vectordb
    except Exception:
        # Corrupt / incompatible store — fall back to a clean rebuild.
        return None


def get_vectordb(
    force_rebuild: bool = False,
    persist_dir: str = "artifacts/kb",
) -> Chroma:
    """
    Retrieve the global vector store instance. Optionally force a rebuild.

    Args:
        force_rebuild: If True, rebuilds the vector store from scratch.
        persist_dir: Directory where the vector store files are persisted.

    Returns:
        Chroma: The loaded or rebuilt vector store.
    """
    global _vectordb

    if force_rebuild:
        print("[vector_store] Forcing KB rebuild...")
        _vectordb = build_vectordb(persist_dir=persist_dir, reset=True)
        return _vectordb

    if _vectordb is None:
        print("[vector_store] Initializing KB...")
        # Prefer loading the persisted store (built by the entrypoint); only build
        # from scratch if there isn't one yet.
        _vectordb = _load_existing_vectordb(persist_dir) or build_vectordb(persist_dir=persist_dir)

    return _vectordb
