# app/rag/vector_store.py
from typing import Optional
from pathlib import Path
import os
import shutil

from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import FakeEmbeddings
from langchain_openai import OpenAIEmbeddings

from .kb_loader import load_sop_documents

_vectordb: Optional[Chroma] = None


def _make_embeddings():
    """
    Choose between real OpenAI embeddings and local fake embeddings.

    - For APP_ENV=local or OPENAI_API_KEY missing/'changeme' -> FakeEmbeddings (no API calls).
    - Otherwise -> OpenAIEmbeddings (real OpenAI API).
    """
    app_env = os.getenv("APP_ENV", "local").lower()
    api_key = os.getenv("OPENAI_API_KEY", "")

    if app_env == "local" or not api_key or api_key == "changeme":
        # Local/dev mode: no OpenAI calls, good for offline & quota issues
        print("[vector_store] Using FakeEmbeddings (local/dev mode, no OpenAI API).")
        return FakeEmbeddings(size=1536)
    else:
        print("[vector_store] Using OpenAIEmbeddings (remote API).")
        return OpenAIEmbeddings()


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
            collection_name="mafd_sop_kb",
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
        collection_name="mafd_sop_kb",
        persist_directory=str(persist_path),
    )

    print("[vector_store] KB build complete.")
    return vectordb


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
        _vectordb = build_vectordb(persist_dir=persist_dir)

    return _vectordb
