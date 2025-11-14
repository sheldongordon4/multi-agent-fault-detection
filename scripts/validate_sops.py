# scripts/validate_sops.py
import sys
from pathlib import Path
from typing import Dict, Tuple, List

SOP_DIR = Path("data/sop")
REQUIRED_KEYS = {"ID", "TITLE"}
OPTIONAL_KEYS = {"SECTION", "URL"}

def parse_header_and_body(text: str) -> Tuple[Dict[str, str], str]:
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

def validate_file(path: Path) -> List[str]:
    errors = []
    text = path.read_text(encoding="utf-8")
    meta, body = parse_header_and_body(text)

    missing_required = REQUIRED_KEYS - set(meta.keys())
    if missing_required:
        errors.append(
            f"{path}: missing required header keys: {', '.join(sorted(missing_required))}"
        )

    if not body.strip():
        errors.append(f"{path}: body/content is empty")

    return errors

def main() -> int:
    if not SOP_DIR.exists():
        print("No data/sop directory found. Nothing to validate.")
        return 0

    all_errors: List[str] = []
    sop_files = [
        p for p in SOP_DIR.glob("**/*")
        if p.is_file() and p.suffix.lower() in {".md", ".txt"}
    ]

    if not sop_files:
        print("No .md or .txt SOP files found in data/sop.")
        return 0

    for path in sop_files:
        errors = validate_file(path)
        if errors:
            all_errors.extend(errors)

    if all_errors:
        print("SOP validation errors found:")
        for e in all_errors:
            print(" -", e)
        print("\nFix the above issues and re-run validation.")
        return 1

    print("All SOP files passed validation.")
    return 0

if __name__ == "__main__":
    sys.exit(main())

