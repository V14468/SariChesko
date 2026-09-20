"""Small, dependency-free export helpers used by views that let the user
export experiment/diagnostic results (Compare Algorithms, History, Reports).

Kept intentionally minimal: SariChesko is local-first, so "export" just means
"write a file somewhere the user chooses on disk" — no cloud, no service calls.
"""
import csv
from pathlib import Path
from typing import Optional, Sequence


def export_rows_to_csv(rows: Sequence[dict], filepath: str, columns: Optional[Sequence[str]] = None) -> str:
    """Write a list of dict rows to a CSV file at `filepath`.

    If `columns` is omitted, the keys of the first row are used as headers,
    in their existing order. Returns the filepath written (as str) so callers
    can show it to the user.
    """
    if not rows:
        raise ValueError("No rows to export")

    cols = list(columns) if columns else list(rows[0].keys())
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)

    return str(path)


def export_text_to_file(text: str, filepath: str) -> str:
    """Write plain text or Markdown content to a file at `filepath`.

    Returns the filepath written (as str) so callers can show it to the user.
    """
    path = Path(filepath)
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as f:
        f.write(text)

    return str(path)


def default_export_dir() -> Path:
    """Default folder to suggest for exports — lives next to the sqlite DB
    so everything SariChesko produces stays under one local data directory."""
    from ..storage.db import get_db_path
    d = get_db_path().parent / "exports"
    d.mkdir(parents=True, exist_ok=True)
    return d