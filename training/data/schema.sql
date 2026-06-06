-- MTG Card Scanner — SQLite schema for cards.sqlite
--
-- Design constraints:
--   - Read-mostly: written once during build, queried millions of times at runtime
--   - On-device: target <100 MB on disk
--   - Two primary access patterns:
--       (a) exact lookup by (set_code, collector_number, language)  — Tier 1
--       (b) fuzzy name search via FTS5 trigram                       — Tier 2
--
-- See learning/data-engineering/sqlite-readmostly-design.md for the rationale
-- behind WITHOUT ROWID, the trigram tokenizer, and the index choices.

PRAGMA user_version = 1;

-- =============================================================================
-- cards: one row per printing per language
-- =============================================================================
-- Primary key: Scryfall UUID (globally unique). WITHOUT ROWID saves space and
-- speeds up PK lookups for TEXT primary keys.
CREATE TABLE cards (
    id                TEXT PRIMARY KEY,           -- Scryfall UUID
    name              TEXT NOT NULL,
    set_code          TEXT NOT NULL,              -- e.g., 'mom', 'lea'
    collector_number  TEXT NOT NULL,              -- e.g., '0123', '12★' — keep as string
    language          TEXT NOT NULL,              -- 'en', 'ja', etc.

    mana_cost         TEXT,                       -- '{2}{U}{U}' or NULL for lands
    type_line         TEXT NOT NULL,              -- 'Creature — Wizard'
    oracle_text       TEXT,                       -- rules text
    power             TEXT,                       -- string: can be '*', '1+*', etc.
    toughness         TEXT,
    rarity            TEXT NOT NULL,              -- 'common', 'uncommon', 'rare', 'mythic', etc.

    layout            TEXT NOT NULL,              -- 'normal', 'transform', 'split', ...
    frame             TEXT,                       -- '1993', '1997', '2003', '2015', 'future'
    finishes          TEXT NOT NULL,              -- JSON array: ["nonfoil","foil","etched"]

    image_uri_normal  TEXT,                       -- Scryfall CDN URL (fetched at runtime)

    FOREIGN KEY (set_code) REFERENCES sets(code)
) WITHOUT ROWID;

-- Tier 1 lookup index — our most-common runtime query:
--   SELECT * FROM cards WHERE set_code=? AND collector_number=? AND language=?
CREATE UNIQUE INDEX idx_cards_lookup
    ON cards(set_code, collector_number, language);

-- Secondary index for name lookups (joined with FTS results).
CREATE INDEX idx_cards_name
    ON cards(name);


-- =============================================================================
-- sets: set metadata
-- =============================================================================
-- Note: icon_uri and parent_code are placeholders for v1. The Scryfall sets
-- endpoint provides richer set metadata than the per-card data; we'll fetch
-- those in a later phase if needed.
CREATE TABLE sets (
    code          TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    released_at   TEXT,                            -- ISO date
    set_type      TEXT,                            -- 'core', 'expansion', 'masters', etc.
    icon_uri      TEXT,                            -- set symbol (TODO: populate via sets endpoint)
    parent_code   TEXT                             -- e.g., promo sets point to their parent
) WITHOUT ROWID;


-- =============================================================================
-- disambiguator_flags: per-card flags for the Phase 6 disambiguator framework
-- =============================================================================
-- When OCR can't distinguish two cards (e.g., same name+set, different finishes),
-- the iOS app loads the specialized model named in `flag_name` to break the tie.
-- args_json carries module-specific arguments (e.g., the sibling card IDs).
CREATE TABLE disambiguator_flags (
    card_id    TEXT NOT NULL,
    flag_name  TEXT NOT NULL,
    args_json  TEXT,                               -- JSON; module-specific
    PRIMARY KEY (card_id, flag_name),
    FOREIGN KEY (card_id) REFERENCES cards(id) ON DELETE CASCADE
) WITHOUT ROWID;


-- =============================================================================
-- meta: build provenance (reproducibility receipt)
-- =============================================================================
-- Records what Scryfall snapshot this DB was built from, what schema version
-- it conforms to, etc. See learning/ml-engineering/reproducible-pipelines.md.
CREATE TABLE meta (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
) WITHOUT ROWID;


-- =============================================================================
-- cards_name_fts: full-text search over card names with trigram tokenizer
-- =============================================================================
-- Trigram tokenizer matches "ightning Bo" against "Lightning Bolt" because they
-- share trigrams — important for partial OCR. Standalone FTS table (no content=
-- link) because cards is WITHOUT ROWID. We insert into both during build.
--
-- Query pattern:
--   SELECT card_id FROM cards_name_fts WHERE name MATCH 'lightning bolt' ORDER BY rank LIMIT 10;
CREATE VIRTUAL TABLE cards_name_fts USING fts5(
    card_id UNINDEXED,
    name,
    tokenize='trigram'
);
