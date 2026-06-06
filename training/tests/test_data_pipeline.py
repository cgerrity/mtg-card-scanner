"""Tests for the Phase 1 data pipeline (schema + normalization + full build)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from data.build_db import build, normalize_card, normalize_set

FIXTURES = Path(__file__).parent / "fixtures"
SCHEMA = Path(__file__).parent.parent / "data" / "schema.sql"


# -----------------------------------------------------------------------------
# Schema sanity
# -----------------------------------------------------------------------------

def test_schema_applies_cleanly(tmp_path: Path) -> None:
    db = tmp_path / "schema_test.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript(SCHEMA.read_text())
    tables = {row[0] for row in conn.execute(
        "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
    )}
    # The four core tables.
    assert {"cards", "sets", "disambiguator_flags", "meta"}.issubset(tables)
    # FTS5 virtual table also creates shadow tables; just verify the main one exists.
    assert "cards_name_fts" in tables
    conn.close()


def test_fts5_trigram_is_available(tmp_path: Path) -> None:
    """FTS5 trigram tokenizer was added in SQLite 3.34. Verify it's present."""
    conn = sqlite3.connect(tmp_path / "fts_test.sqlite")
    try:
        conn.execute(
            "CREATE VIRTUAL TABLE _tt USING fts5(x, tokenize='trigram')"
        )
    finally:
        conn.close()


# -----------------------------------------------------------------------------
# normalize_card
# -----------------------------------------------------------------------------

def _english_card() -> dict:
    return {
        "id": "test-id",
        "name": "Lightning Bolt",
        "set": "lea",
        "set_name": "Limited Edition Alpha",
        "collector_number": "161",
        "lang": "en",
        "mana_cost": "{R}",
        "type_line": "Instant",
        "oracle_text": "Lightning Bolt deals 3 damage to any target.",
        "rarity": "common",
        "layout": "normal",
        "frame": "1993",
        "finishes": ["nonfoil"],
        "image_uris": {"normal": "https://example.test/img.jpg"},
    }


def test_normalize_english_card_kept() -> None:
    out = normalize_card(_english_card())
    assert out is not None
    assert out["id"] == "test-id"
    assert out["name"] == "Lightning Bolt"
    assert out["set_code"] == "lea"
    assert out["collector_number"] == "161"
    assert out["language"] == "en"
    assert out["image_uri_normal"] == "https://example.test/img.jpg"
    # finishes is stored as JSON string per schema
    assert out["finishes"] == '["nonfoil"]'


def test_normalize_non_english_filtered() -> None:
    raw = _english_card() | {"lang": "ja"}
    assert normalize_card(raw) is None


def test_normalize_missing_lang_filtered() -> None:
    raw = {k: v for k, v in _english_card().items() if k != "lang"}
    assert normalize_card(raw) is None


def test_normalize_dfc_uses_front_face_image() -> None:
    raw = {
        "id": "dfc-test",
        "name": "Westvale Abbey // Ormendahl, Profane Prince",
        "set": "soi",
        "set_name": "Shadows over Innistrad",
        "collector_number": "281",
        "lang": "en",
        "type_line": "Land // Creature — Demon Horror",
        "rarity": "rare",
        "layout": "transform",
        "frame": "2015",
        "finishes": ["nonfoil", "foil"],
        "card_faces": [
            {"name": "Westvale Abbey",
             "image_uris": {"normal": "https://example.test/front.jpg"}},
            {"name": "Ormendahl, Profane Prince",
             "image_uris": {"normal": "https://example.test/back.jpg"}},
        ],
    }
    out = normalize_card(raw)
    assert out is not None
    assert out["image_uri_normal"] == "https://example.test/front.jpg"


def test_normalize_set_extracts_fields() -> None:
    out = normalize_set(_english_card() | {"released_at": "1993-08-05", "set_type": "core"})
    assert out == {
        "code": "lea",
        "name": "Limited Edition Alpha",
        "released_at": "1993-08-05",
        "set_type": "core",
        "icon_uri": None,
        "parent_code": None,
    }


# -----------------------------------------------------------------------------
# Full build pipeline against the fixture
# -----------------------------------------------------------------------------

@pytest.fixture
def built_db(tmp_path: Path) -> Path:
    """Run the full build against the fixture, return the resulting DB path."""
    db_path = tmp_path / "test_cards.sqlite"
    build(
        json_path=FIXTURES / "sample_bulk.json",
        db_path=db_path,
        schema_path=SCHEMA,
    )
    return db_path


def test_build_creates_expected_row_count(built_db: Path) -> None:
    conn = sqlite3.connect(built_db)
    n_cards = conn.execute("SELECT COUNT(*) FROM cards").fetchone()[0]
    # Fixture has 6 cards; 1 is Japanese and gets filtered. So we expect 5.
    assert n_cards == 5
    n_sets = conn.execute("SELECT COUNT(*) FROM sets").fetchone()[0]
    # Sets in the fixture: lea, leb, soi (Japanese card is from lea but filtered
    # out — set still seen from the English Lightning Bolt). So 3 sets total.
    assert n_sets == 3
    conn.close()


def test_build_tier1_lookup(built_db: Path) -> None:
    conn = sqlite3.connect(built_db)
    row = conn.execute(
        "SELECT name FROM cards WHERE set_code=? AND collector_number=? AND language=?",
        ("lea", "161", "en"),
    ).fetchone()
    assert row is not None
    assert row[0] == "Lightning Bolt"

    # Different set, same collector number — independent row.
    row = conn.execute(
        "SELECT name FROM cards WHERE set_code=? AND collector_number=? AND language=?",
        ("leb", "162", "en"),
    ).fetchone()
    assert row is not None
    assert row[0] == "Lightning Bolt"

    # DFC lookup.
    row = conn.execute(
        "SELECT name FROM cards WHERE set_code=? AND collector_number=? AND language=?",
        ("soi", "281", "en"),
    ).fetchone()
    assert row is not None
    assert row[0].startswith("Westvale Abbey")
    conn.close()


def test_build_fts_trigram_search(built_db: Path) -> None:
    conn = sqlite3.connect(built_db)

    # Exact name should match.
    matches = conn.execute(
        "SELECT card_id FROM cards_name_fts WHERE name MATCH ? ORDER BY rank LIMIT 10",
        ("Lightning Bolt",),
    ).fetchall()
    assert len(matches) == 2  # both Lightning Bolts (lea + leb)

    # Partial match via trigram tokenizer.
    matches = conn.execute(
        "SELECT card_id FROM cards_name_fts WHERE name MATCH ? ORDER BY rank LIMIT 10",
        ("Mox",),
    ).fetchall()
    assert len(matches) == 2  # both Mox Pearls

    conn.close()


def test_build_emits_disambiguator_flags_for_ambiguous_pair(built_db: Path) -> None:
    conn = sqlite3.connect(built_db)
    # Both Mox Pearls share (name='Mox Pearl', set='lea') and should be flagged.
    flag_card_ids = {
        row[0]
        for row in conn.execute(
            "SELECT card_id FROM disambiguator_flags WHERE flag_name='needs_disambiguation'"
        )
    }
    assert flag_card_ids == {"card-mox-pearl-a", "card-mox-pearl-b"}

    # Each flag row's args_json names the OTHER card as its sibling.
    import json as _json  # local import to avoid affecting other tests
    rows = list(conn.execute(
        "SELECT card_id, args_json FROM disambiguator_flags "
        "WHERE flag_name='needs_disambiguation' ORDER BY card_id"
    ))
    args_a = _json.loads(rows[0][1])
    args_b = _json.loads(rows[1][1])
    assert args_a["siblings"] == ["card-mox-pearl-b"]
    assert args_b["siblings"] == ["card-mox-pearl-a"]

    # Lightning Bolt printings in different sets are NOT ambiguous —
    # they have different set_codes, so Tier 1 distinguishes them.
    bolt_flags = conn.execute(
        "SELECT COUNT(*) FROM disambiguator_flags "
        "WHERE card_id IN ('card-bolt-lea-161','card-bolt-leb-162')"
    ).fetchone()[0]
    assert bolt_flags == 0
    conn.close()


def test_build_records_provenance_in_meta(built_db: Path) -> None:
    conn = sqlite3.connect(built_db)
    meta = dict(conn.execute("SELECT key, value FROM meta"))
    assert meta.get("db_version") == "1"
    # Source-file metadata is always populated; SHA/updated_at only present if
    # the .meta.json sidecar exists (fixture doesn't have one).
    assert meta.get("source_file") == "sample_bulk.json"
    assert int(meta["source_size_bytes"]) > 0
    conn.close()


def test_build_is_idempotent_at_logical_level(tmp_path: Path) -> None:
    """Two builds from the same fixture produce the same logical content.

    (Byte-equality of SQLite files isn't expected — SQLite encodes metadata
    that varies. Logical equality is what we care about.)
    """
    db1 = tmp_path / "first.sqlite"
    db2 = tmp_path / "second.sqlite"
    fixture = FIXTURES / "sample_bulk.json"

    build(json_path=fixture, db_path=db1, schema_path=SCHEMA)
    build(json_path=fixture, db_path=db2, schema_path=SCHEMA)

    c1 = sqlite3.connect(db1)
    c2 = sqlite3.connect(db2)
    cards1 = set(c1.execute("SELECT id, name, set_code, collector_number FROM cards"))
    cards2 = set(c2.execute("SELECT id, name, set_code, collector_number FROM cards"))
    assert cards1 == cards2

    flags1 = set(c1.execute(
        "SELECT card_id, flag_name FROM disambiguator_flags ORDER BY card_id, flag_name"
    ))
    flags2 = set(c2.execute(
        "SELECT card_id, flag_name FROM disambiguator_flags ORDER BY card_id, flag_name"
    ))
    assert flags1 == flags2
    c1.close()
    c2.close()
