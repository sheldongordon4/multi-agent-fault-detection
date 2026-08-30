"""Rebuild the local SOP knowledge base from the source markdown files."""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load environment variables from .env (including OPENAI_API_KEY)
load_dotenv(ROOT / ".env")

from app.rag.vector_store import build_vectordb  # noqa: E402


def main() -> None:
    """Force a clean rebuild of the vector store used for KB retrieval."""
    artifacts_dir = Path("artifacts/kb")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    vectordb = build_vectordb(persist_dir=str(artifacts_dir), reset=True)

    # Touch the collection so Chroma materializes it even when the DB is empty.
    try:
        _ = vectordb._collection.count()  # type: ignore[attr-defined]
    except Exception:  # pragma: no cover - Chroma internals vary by version.
        pass

    print("[refresh_kb] Rebuilt KB vector store from data/sop into artifacts/kb")


if __name__ == "__main__":
    main()
