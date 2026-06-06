"""
Download Scryfall bulk card data.

Scryfall (https://scryfall.com) publishes "bulk data" files: large JSON
dumps of their entire card catalog, refreshed daily. We use the
`default_cards` bulk type, which contains one record per (set, collector#)
combination. Reference: https://scryfall.com/docs/api/bulk-data

This script:
  1. Hits Scryfall's bulk-data metadata endpoint to find the latest URL.
  2. Stream-downloads the JSON file to artifacts/ (don't OOM on a 500 MB+ download).
  3. Computes a SHA256 as it streams (no second pass needed).
  4. Writes a sidecar metadata file recording version + hash, for reproducibility.
  5. Is idempotent: if the latest version is already on disk, it does nothing.

Usage:
    python -m data.scryfall_download              # download default_cards
    python -m data.scryfall_download --force      # re-download even if cached
    python -m data.scryfall_download --bulk-type all_cards   # different bulk type

See PLAN.md § 5 Phase 1 and learning/ml-engineering/reproducible-pipelines.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import requests

BULK_DATA_API: Final = "https://api.scryfall.com/bulk-data"
DEFAULT_BULK_TYPE: Final = "default_cards"
ARTIFACTS_DIR: Final = Path(__file__).resolve().parent.parent / "artifacts"

# Scryfall requires User-Agent + Accept on every API request — without these,
# requests are rejected with 400. https://scryfall.com/docs/api
SCRYFALL_HEADERS: Final = {
    "User-Agent": "MTGCardScanner/0.1 (+https://github.com/cgerrity/mtg-card-scanner)",
    "Accept": "application/json",
}


def fetch_bulk_metadata(bulk_type: str) -> dict:
    """Return the Scryfall bulk-data entry of the given type."""
    resp = requests.get(BULK_DATA_API, headers=SCRYFALL_HEADERS, timeout=30)
    resp.raise_for_status()
    payload = resp.json()
    for entry in payload["data"]:
        if entry["type"] == bulk_type:
            return entry
    available = sorted(e["type"] for e in payload["data"])
    raise RuntimeError(
        f"No bulk entry of type {bulk_type!r} at {BULK_DATA_API}. "
        f"Available types: {available}"
    )


def stream_download(url: str, dest: Path, *, chunk_size: int = 1 << 16) -> str:
    """Stream-download `url` to `dest`, return its sha256 hex digest.

    Streaming matters: the bulk JSON is hundreds of MB. A naive `resp.content`
    would buffer the entire response in memory. Atomic rename at the end so
    a partial download isn't mistaken for a complete one on the next run.
    """
    sha = hashlib.sha256()
    tmp = dest.with_suffix(dest.suffix + ".partial")
    bytes_seen = 0
    progress = _make_progress_printer()

    with requests.get(url, stream=True, headers=SCRYFALL_HEADERS, timeout=60) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("Content-Length", "0"))
        with tmp.open("wb") as fh:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if not chunk:
                    continue
                fh.write(chunk)
                sha.update(chunk)
                bytes_seen += len(chunk)
                progress(bytes_seen, total)

    if sys.stderr.isatty():
        print(file=sys.stderr)  # newline after the inline progress line
    tmp.rename(dest)  # atomic
    return sha.hexdigest()


def _make_progress_printer():
    """Return a progress function that:
       - rewrites a single line if stderr is a TTY (interactive use), or
       - prints one line per ~25 MB chunk otherwise (non-interactive: pipes,
         logs, CI captures). This keeps logs sane when piped.
    """
    is_tty = sys.stderr.isatty()
    last_logged_mb = 0.0
    log_every_mb = 25.0

    def progress(seen: int, total: int) -> None:
        nonlocal last_logged_mb
        seen_mb = seen / 1e6
        if is_tty:
            if total > 0:
                msg = f"\r  {seen_mb:>7.1f} MB / {total / 1e6:.1f} MB ({100 * seen / total:5.1f}%)"
            else:
                msg = f"\r  {seen_mb:>7.1f} MB (size unknown)"
            sys.stderr.write(msg)
            sys.stderr.flush()
        else:
            if seen_mb - last_logged_mb >= log_every_mb:
                if total > 0:
                    print(
                        f"  {seen_mb:>7.1f} MB / {total / 1e6:.1f} MB "
                        f"({100 * seen / total:5.1f}%)",
                        file=sys.stderr,
                    )
                else:
                    print(f"  {seen_mb:>7.1f} MB downloaded", file=sys.stderr)
                last_logged_mb = seen_mb

    return progress


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Scryfall bulk card data.")
    parser.add_argument(
        "--bulk-type",
        default=DEFAULT_BULK_TYPE,
        help=f"Scryfall bulk type to download (default: {DEFAULT_BULK_TYPE!r}).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download even if a current copy is already on disk.",
    )
    args = parser.parse_args()

    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    data_path = ARTIFACTS_DIR / f"scryfall_{args.bulk_type}.json"
    meta_path = ARTIFACTS_DIR / f"scryfall_{args.bulk_type}.meta.json"

    print(f"[scryfall] Fetching bulk metadata for {args.bulk_type!r}...")
    meta = fetch_bulk_metadata(args.bulk_type)
    remote_updated_at = meta["updated_at"]
    download_uri = meta["download_uri"]
    size_mb = meta.get("size", 0) / 1e6

    # Idempotency: if we already have this exact version, skip.
    if not args.force and meta_path.exists() and data_path.exists():
        cached = json.loads(meta_path.read_text())
        if cached.get("updated_at") == remote_updated_at:
            print(
                f"[scryfall] Already have {args.bulk_type!r} at {remote_updated_at}; "
                f"skipping (use --force to re-download)."
            )
            return 0

    print(f"[scryfall] Downloading ~{size_mb:.1f} MB from {download_uri}")
    sha256 = stream_download(download_uri, data_path)

    # Record what we downloaded — essential for reproducibility.
    sidecar = {
        "bulk_type": args.bulk_type,
        "updated_at": remote_updated_at,
        "download_uri": download_uri,
        "sha256": sha256,
        "size_bytes": data_path.stat().st_size,
        "downloaded_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    meta_path.write_text(json.dumps(sidecar, indent=2) + "\n")

    print(f"[scryfall] Saved {data_path.name} ({data_path.stat().st_size / 1e6:.1f} MB)")
    print(f"[scryfall] Metadata at {meta_path.name}")
    print(f"[scryfall] SHA256: {sha256}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
