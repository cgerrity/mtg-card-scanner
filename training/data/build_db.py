"""
Build cards.sqlite from the downloaded Scryfall bulk JSON.

Pipeline:
  1. Stream-parse the bulk JSON (it's hundreds of MB; naive json.load OOMs).
  2. Filter cards to scope (currently: English only).
  3. Normalize fields into our schema.
  4. Insert in batches (single transaction per batch for speed).
  5. After all inserts, detect ambiguous (name, set_code) pairs and emit
     disambiguator flag rows for the Phase 6 module framework.
  6. Record build provenance in the `meta` table.
  7. ANALYZE + VACUUM to optimize for read-mostly workload.

Idempotent: re-running rebuilds the DB from scratch.

Usage:
    python -m data.build_db                  # default: read scryfall_default_cards.json
    python -m data.build_db --bulk-type all_cards --db-name cards.sqlite

See PLAN.md § 5 Phase 1 and learning/data-engineering/sqlite-readmostly-design.md.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Final

import ijson

ARTIFACTS_DIR: Final = Path(__file__).resolve().parent.parent / "artifacts"
SCHEMA_PATH: Final = Path(__file__).resolve().parent / "schema.sql"
BATCH_SIZE: Final = 5000

# Languages we keep on-device. The schema supports any string; for v1 we are
# English-only and visually flag non-English cards at scan time. See PLAN.md.
IN_SCOPE_LANGUAGES: Final = {"en"}


def iter_cards(json_path: Path) -> Iterator[dict[str, Any]]:
    """Yield card dicts from the Scryfall bulk JSON, streaming.

    Scryfall bulk files are top-level JSON arrays of card objects. The 'item'
    prefix in ijson means "each element of the top-level array".
    """
    with json_path.open("rb") as fh:
        yield from ijson.items(fh, "item")


def normalize_card(raw: dict[str, Any]) -> dict[str, Any] | None:
    """Convert a raw Scryfall card into a row for our `cards` table.

    Returns None if the card is out of scope (currently: non-English).
    """
    if raw.get("lang") not in IN_SCOPE_LANGUAGES:
        return None

    # Most cards have image_uris at top level. Double-faced cards (transform,
    # MDFC) put image_uris on each face — take the front face as the canonical
    # image for display in the confirmation UI.
    image_uri = (raw.get("image_uris") or {}).get("normal")
    if image_uri is None and raw.get("card_faces"):
        front_face = raw["card_faces"][0]
        image_uri = (front_face.get("image_uris") or {}).get("normal")

    return {
        "id": raw["id"],
        "name": raw["name"],
        "set_code": raw["set"],
        "collector_number": raw["collector_number"],
        "language": raw["lang"],
        "mana_cost": raw.get("mana_cost"),
        "type_line": raw.get("type_line", ""),
        "oracle_text": raw.get("oracle_text"),
        "power": raw.get("power"),
        "toughness": raw.get("toughness"),
        "rarity": raw["rarity"],
        "layout": raw["layout"],
        "frame": raw.get("frame"),
        "finishes": json.dumps(raw.get("finishes", [])),
        "image_uri_normal": image_uri,
    }


def normalize_set(raw_card: dict[str, Any]) -> dict[str, Any]:
    """Extract a set row from a card (Scryfall denormalizes set info onto each card)."""
    return {
        "code": raw_card["set"],
        "name": raw_card["set_name"],
        "released_at": raw_card.get("released_at"),
        "set_type": raw_card.get("set_type"),
        "icon_uri": None,        # TODO: populate via Scryfall /sets endpoint
        "parent_code": None,     # TODO: same
    }


INSERT_CARD_SQL: Final = """
    INSERT INTO cards (
        id, name, set_code, collector_number, language,
        mana_cost, type_line, oracle_text, power, toughness, rarity,
        layout, frame, finishes, image_uri_normal
    ) VALUES (
        :id, :name, :set_code, :collector_number, :language,
        :mana_cost, :type_line, :oracle_text, :power, :toughness, :rarity,
        :layout, :frame, :finishes, :image_uri_normal
    )
"""

INSERT_FTS_SQL: Final = "INSERT INTO cards_name_fts (card_id, name) VALUES (?, ?)"

INSERT_SET_SQL: Final = """
    INSERT INTO sets (code, name, released_at, set_type, icon_uri, parent_code)
    VALUES (:code, :name, :released_at, :set_type, :icon_uri, :parent_code)
"""


def build(json_path: Path, db_path: Path, schema_path: Path) -> None:
    """Build cards.sqlite from scratch."""
    if db_path.exists():
        db_path.unlink()  # rebuild deterministically

    conn = sqlite3.connect(db_path)
    conn.executescript(schema_path.read_text())

    sets_seen: dict[str, dict[str, Any]] = {}
    cards_buf: list[dict[str, Any]] = []
    fts_buf: list[tuple[str, str]] = []

    n_total = 0
    n_kept = 0

    def flush_cards() -> None:
        if not cards_buf:
            return
        with conn:
            conn.executemany(INSERT_CARD_SQL, cards_buf)
            conn.executemany(INSERT_FTS_SQL, fts_buf)
        cards_buf.clear()
        fts_buf.clear()

    print(f"[build_db] Streaming {json_path.name}...")
    for raw in iter_cards(json_path):
        n_total += 1
        normalized = normalize_card(raw)
        if normalized is None:
            continue
        n_kept += 1
        cards_buf.append(normalized)
        fts_buf.append((normalized["id"], normalized["name"]))

        set_code = raw["set"]
        if set_code not in sets_seen:
            sets_seen[set_code] = normalize_set(raw)

        if len(cards_buf) >= BATCH_SIZE:
            flush_cards()
        if n_total % 50_000 == 0:
            print(f"  ... read {n_total:>8,} cards (kept {n_kept:>8,})")

    flush_cards()
    print(f"[build_db] Streamed {n_total:,} cards, kept {n_kept:,} after filtering.")

    # Insert all sets we encountered.
    with conn:
        conn.executemany(INSERT_SET_SQL, list(sets_seen.values()))
    print(f"[build_db] Inserted {len(sets_seen):,} sets.")

    # Detect ambiguous (name, set_code) pairs. These are cards that share name +
    # set but differ in some other dimension (finish, frame, art). When OCR can
    # only see name + set (Tier 2 of identification), we need a disambiguator.
    print("[build_db] Detecting ambiguous (name, set_code) pairs...")
    ambiguous_pairs = conn.execute(
        "SELECT name, set_code FROM cards GROUP BY name, set_code HAVING COUNT(*) > 1"
    ).fetchall()
    n_flags = 0
    with conn:
        for name, set_code in ambiguous_pairs:
            card_ids = [
                row[0]
                for row in conn.execute(
                    "SELECT id FROM cards WHERE name=? AND set_code=?",
                    (name, set_code),
                )
            ]
            for cid in card_ids:
                siblings = [other for other in card_ids if other != cid]
                conn.execute(
                    "INSERT INTO disambiguator_flags (card_id, flag_name, args_json) "
                    "VALUES (?, ?, ?)",
                    (cid, "needs_disambiguation", json.dumps({"siblings": siblings})),
                )
                n_flags += 1
    print(
        f"[build_db] {len(ambiguous_pairs):,} ambiguous (name, set) pairs "
        f"→ {n_flags:,} disambiguator flag rows."
    )

    # Build provenance — the reproducibility receipt.
    sidecar = json_path.with_suffix(".meta.json")
    if sidecar.exists():
        src_meta = json.loads(sidecar.read_text())
    else:
        src_meta = {}
    with conn:
        conn.executemany(
            "INSERT INTO meta (key, value) VALUES (?, ?)",
            [
                ("db_version", "1"),
                ("scryfall_updated_at", src_meta.get("updated_at", "")),
                ("scryfall_sha256", src_meta.get("sha256", "")),
                ("source_file", json_path.name),
                ("source_size_bytes", str(json_path.stat().st_size)),
            ],
        )

    # Optimize: ANALYZE updates query planner statistics; VACUUM reclaims space.
    # Both need to run outside an active transaction — switch to autocommit.
    conn.isolation_level = None
    conn.execute("ANALYZE")
    conn.execute("VACUUM")
    conn.close()

    final_mb = db_path.stat().st_size / 1e6
    print(f"[build_db] Built {db_path.name} — {final_mb:.1f} MB.")
    if final_mb > 100:
        print(f"[build_db] WARNING: DB size {final_mb:.1f} MB exceeds 100 MB budget.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cards.sqlite from Scryfall bulk JSON.")
    parser.add_argument(
        "--bulk-type",
        default="default_cards",
        help="Scryfall bulk type the source file is named after (default: default_cards).",
    )
    parser.add_argument(
        "--db-name",
        default="cards.sqlite",
        help="Output filename (placed in artifacts/).",
    )
    args = parser.parse_args()

    json_path = ARTIFACTS_DIR / f"scryfall_{args.bulk_type}.json"
    db_path = ARTIFACTS_DIR / args.db_name

    if not json_path.exists():
        print(f"[build_db] {json_path} not found. Run scryfall_download.py first.")
        return 1

    build(json_path, db_path, SCHEMA_PATH)
    return 0


if __name__ == "__main__":
    sys.exit(main())
