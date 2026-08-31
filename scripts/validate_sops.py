"""Basic validation checks for markdown-based SOP documents used by the KB."""

from __future__ import annotations

import sys
from pathlib import Path

SOP_DIR = Path("data/sop")
REQUIRED_KEYS = {"ID", "TITLE"}
OPTIONAL_KEYS = {"SECTION", "URL"}


def parse_header_and_body(text: str) -> tuple[dict[str, str], str]:
    """Split a simple header block from the body content."""
    lines = text.splitlines()
    meta: dict[str, str] = {}
    body_start_idx = 0

    for index, line in enumerate(lines):
        if not line.strip():
            body_start_idx = index + 1
            break
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().upper()] = value.strip()
        else:
            body_start_idx = index
            break

    body = "\n".join(lines[body_start_idx:])
    return meta, body


def validate_file(path: Path) -> list[str]:
    """Return a list of validation errors for a single SOP file."""
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    meta, body = parse_header_and_body(text)

    missing_required = REQUIRED_KEYS - set(meta)
    if missing_required:
        errors.append(
            f"{path}: missing required header keys: {', '.join(sorted(missing_required))}"
        )

    if not body.strip():
        errors.append(f"{path}: body/content is empty")

    return errors


def iter_sop_files() -> list[Path]:
    """Return all markdown/text SOP files under the data/sop tree."""
    if not SOP_DIR.exists():
        return []
    return [
        path
        for path in SOP_DIR.glob("**/*")
        if path.is_file() and path.suffix.lower() in {".md", ".txt"}
    ]


def main() -> int:
    if not SOP_DIR.exists():
        print("No data/sop directory found. Nothing to validate.")
        return 0

    sop_files = iter_sop_files()
    if not sop_files:
        print("No .md or .txt SOP files found in data/sop.")
        return 0

    all_errors: list[str] = []
    for path in sop_files:
        all_errors.extend(validate_file(path))

    if all_errors:
        print("SOP validation errors found:")
        for error in all_errors:
            print(" -", error)
        print("\nFix the above issues and re-run validation.")
        return 1

    print("All SOP files passed validation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
