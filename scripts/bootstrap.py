"""
One-command prep for a local end-to-end run.

Run AFTER the infra is up and the schema is migrated:
    docker compose -f docker-compose.dev.yaml up -d
    alembic -c app/alembic.ini upgrade head
    .venv/Scripts/python.exe scripts/bootstrap.py

Creates Kafka topics, trains the ML models if missing, and (re)builds the SOP
knowledge base. Idempotent — safe to re-run.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> None:
    print("[bootstrap] ensuring Kafka topics...")
    from app.kafka.admin import ensure_topics

    ensure_topics()

    print("[bootstrap] event detector (train if missing)...")
    from app.ml.fault_detector import load_testbed_model, train_isoforest_on_testbed

    try:
        load_testbed_model()
        print("  event model present.")
    except FileNotFoundError:
        train_isoforest_on_testbed("data/generated/normal_train_013.csv")

    print("[bootstrap] fault classifier (train if missing)...")
    from app.ml.fault_classifier import load_classifier, train_classifier

    try:
        load_classifier()
        print("  classifier present.")
    except FileNotFoundError:
        train_classifier()

    print("[bootstrap] building SOP knowledge base (Chroma + bge-small)...")
    from app.rag.vector_store import get_vectordb

    get_vectordb(force_rebuild=True)

    print("[bootstrap] done.")


if __name__ == "__main__":
    main()
