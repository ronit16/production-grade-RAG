#!/usr/bin/env python3
"""
Download real public documents for evaluation fixtures.

Run once locally, then commit the results:
    python tests/evaluation/download_fixtures.py
    git add tests/evaluation/fixtures/docs/
    git commit -m "Add real-document evaluation fixtures (TXT, MD, PDF, DOCX, HTML)"

Documents are committed to git so CI has no network dependency.
Each file type exercises a different parser path in the Unstructured ingestion worker.
"""
from __future__ import annotations

from pathlib import Path

try:
    import httpx
except ImportError:
    import sys
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "httpx", "-q"])
    import httpx

DOCS_DIR = Path(__file__).parent / "fixtures" / "docs"
DOCS_DIR.mkdir(parents=True, exist_ok=True)

SOURCES = [
    # ── TXT ──────────────────────────────────────────────────────────────────
    {
        "filename": "rfc9110_excerpt.txt",
        "url": "https://www.rfc-editor.org/rfc/rfc9110.txt",
        "max_bytes": 65_536,
        "description": "RFC 9110 — HTTP Semantics (TXT)",
    },
    {
        "filename": "python312_whatsnew.txt",
        "url": "https://docs.python.org/3/whatsnew/3.12.txt",
        "max_bytes": 32_768,
        "description": "Python 3.12 What's New (TXT)",
    },
    # ── Markdown ──────────────────────────────────────────────────────────────
    {
        "filename": "fastapi_readme.md",
        "url": "https://raw.githubusercontent.com/fastapi/fastapi/master/README.md",
        "max_bytes": 30_720,
        "description": "FastAPI README (Markdown)",
    },
    # ── HTML / Web page ───────────────────────────────────────────────────────
    {
        "filename": "transformer_wikipedia.html",
        "url": "https://en.wikipedia.org/wiki/Transformer_(deep_learning_architecture)",
        "max_bytes": 131_072,
        "description": "Wikipedia: Transformer architecture (HTML)",
        "headers": {
            "User-Agent": "Mozilla/5.0 (evaluation-fixture-downloader; educational use)",
            "Accept": "text/html",
        },
    },
    # ── PDF ───────────────────────────────────────────────────────────────────
    {
        "filename": "cc_by_40_legalcode.pdf",
        "url": "https://creativecommons.org/licenses/by/4.0/legalcode.pdf",
        "max_bytes": 524_288,  # 512 KB — keep full PDF so Unstructured can parse it
        "description": "Creative Commons BY 4.0 Legal Code (PDF)",
    },
]

# ── DOCX: NIST SP 800-53r5 Quick-Start Guide ─────────────────────────────────
# Download from NIST directly. URL may change — check csrc.nist.gov if it fails.
NIST_DOCX = {
    "filename": "nist_controls_excerpt.docx",
    "url": (
        "https://csrc.nist.gov/csrc/media/Publications/sp/800-53/rev-5/"
        "final/documents/sp800-53r5-quick-start-guide.docx"
    ),
    "max_bytes": 1_048_576,  # 1 MB
    "description": "NIST SP 800-53r5 Quick-Start Guide (DOCX)",
}


def download(source: dict) -> None:
    target = DOCS_DIR / source["filename"]
    if target.exists():
        size = target.stat().st_size
        print(f"  [skip] {source['filename']} already exists ({size:,} bytes)")
        return

    print(f"  [fetch] {source['description']} → {source['filename']}")
    headers = source.get("headers", {})
    try:
        r = httpx.get(source["url"], timeout=60, follow_redirects=True, headers=headers)
        r.raise_for_status()
    except httpx.HTTPError as exc:
        print(f"  [FAIL]  {exc}")
        return

    data = r.content[: source["max_bytes"]]
    target.write_bytes(data)
    print(f"  [ok]   {len(data):,} bytes → {target.name}")


def main() -> None:
    print(f"Downloading evaluation fixtures to: {DOCS_DIR}\n")
    for s in SOURCES:
        download(s)
    download(NIST_DOCX)
    print(
        "\nDone. Now commit:\n"
        "  git add tests/evaluation/fixtures/docs/\n"
        '  git commit -m "Add real-document evaluation fixtures"'
    )


if __name__ == "__main__":
    main()
