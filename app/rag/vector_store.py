import shutil
from pathlib import Path

from langchain_community.vectorstores import Chroma
from langchain_huggingface import HuggingFaceEmbeddings

from app.rag.config import settings

from .kb_loader import load_sop_documents

_vectordb: Chroma | None = None

# Local, open-source embedding model (self-hosted, no API). Configured in
# app/rag/config.py. Changing it requires rebuilding the vector DB (dim change).
EMBEDDING_MODEL = settings.EMBEDDING_MODEL

COLLECTION_NAME = "mafd_sop_kb"


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

    texts = [d["content"] for d in docs]
    metadatas = [d["metadata"] for d in docs]

    print(f"[vector_store] Building KB from {len(texts)} SOP document(s)...")

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
