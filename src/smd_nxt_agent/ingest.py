"""Finds datasheet PDFs to process."""

from __future__ import annotations

from pathlib import Path


def list_pdfs(folder: Path) -> list[Path]:
    return sorted(p for p in folder.glob("*.pdf") if p.is_file())
