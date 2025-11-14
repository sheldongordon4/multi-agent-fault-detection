# scripts/refresh_kb.py

from pathlib import Path
import sys

from dotenv import load_dotenv

# Ensure project root is on PYTHONPATH so "app" can be imported
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Load environment variables from .env (including OPENAI_API_KEY)
load_dotenv(ROOT / ".env")

from app.rag.vector_store import build_vectordb  # noqa: E402


def main() -> None:
    artifacts_dir = Path("artifacts/kb")
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    # Force a clean rebuild of the KB
    vectordb = build_vectordb(persist_dir=str(artifacts_dir), reset=True)
    # Touch the collection so Chroma materializes it
    try:
        _ = vectordb._collection.count()  # type: ignore[attr-defined]
    except Exception:
        pass

    print("[refresh_kb] Rebuilt KB vector store from data/sop into artifacts/kb")


if __name__ == "__main__":
    main()
