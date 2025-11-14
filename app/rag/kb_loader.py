# app/rag/kb_loader.py
import os
from pathlib import Path
from typing import List, Dict, Tuple

SOP_DIR = Path("data/sop")
REQUIRED_KEYS = {"ID", "TITLE"}

def _parse_header_and_body(text: str) -> Tuple[Dict[str, str], str]:
    """
    Very simple header parser.
    Reads lines until it hits a blank line, interprets 'KEY: value'.
    Returns (metadata_dict, body_text).
    """
    lines = text.splitlines()
    meta = {}
    body_start_idx = 0

    for i, line in enumerate(lines):
        if not line.strip():
            body_start_idx = i + 1
            break
        if ":" in line:
            key, val = line.split(":", 1)
            meta[key.strip().upper()] = val.strip()
        else:
            body_start_idx = i
            break

    body = "\n".join(lines[body_start_idx:])
    return meta, body

def load_sop_documents() -> List[Dict]:
    """
    Walks data/sop and returns a list of dicts:
    {
      'content': <body_text>,
      'metadata': {
        'source_id': ...,
        'title': ...,
        'section': ...,
        'url': ...,
        'path': ...
      }
    }

    Files missing required headers (ID, TITLE) are skipped with a warning.
    """
    docs: List[Dict] = []

    if not SOP_DIR.exists():
        print("[kb_loader] data/sop does not exist. No SOP documents loaded.")
        return docs

    sop_files = [
        p for p in SOP_DIR.glob("**/*")
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}
    ]

    if not sop_files:
        print("[kb_loader] No .md or .txt SOP files found in data/sop.")
        return docs

    for path in sop_files:
        try:
            text = path.read_text(encoding="utf-8")
        except Exception as e:
            print(f"[kb_loader] Failed to read {path}: {e}")
            continue

        raw_meta, body = _parse_header_and_body(text)

        missing_required = REQUIRED_KEYS - set(raw_meta.keys())
        if missing_required:
            print(
                f"[kb_loader] Skipping {path}: missing required header keys "
                f"{', '.join(sorted(missing_required))}"
            )
            continue

        if not body.strip():
            print(f"[kb_loader] Skipping {path}: empty body/content.")
            continue

        meta = {
            "source_id": raw_meta["ID"],
            "title": raw_meta["TITLE"],
            "section": raw_meta.get("SECTION"),
            "url": raw_meta.get("URL"),
            "path": str(path),
        }

        docs.append({"content": body, "metadata": meta})

    print(f"[kb_loader] Loaded {len(docs)} SOP document(s) from data/sop.")
    return docs
