"""DDL for the dated legal store.

Hard rule (CLAUDE.md #1): every fact row has valid_from, valid_to, source_file, page.
Enforced in the database with NOT NULL + CHECK, not only in Python.
Open-ended validity is stored as the sentinel OPEN_END ('9999-12-31'), never NULL.
"""

OPEN_END = "9999-12-31"

# Shared "fact" columns, appended to every fact table.
FACT_COLS = """
    valid_from  TEXT    NOT NULL
        CHECK (date(valid_from) IS NOT NULL AND date(valid_from) = valid_from),
    valid_to    TEXT    NOT NULL
        CHECK (date(valid_to) IS NOT NULL AND date(valid_to) = valid_to),
    source_file TEXT    NOT NULL
        CHECK (typeof(source_file) = 'text' AND length(trim(source_file)) > 0),
    page        INTEGER NOT NULL
        CHECK (typeof(page) = 'integer' AND page >= 1),
    CHECK (valid_to >= valid_from)
"""

STATUS_COL = """status TEXT NOT NULL DEFAULT 'accepted'
        CHECK (status IN ('accepted','needs_review','verified'))"""

# Columns shared by the four code-keyed rule tables (rd, acd, sales tax, income tax).
HIER_COLS = """
    code_norm   TEXT
        CHECK (code_norm IS NULL OR code_norm = '' OR code_norm NOT GLOB '*[^0-9]*'),
    match_level TEXT    NOT NULL
        CHECK (match_level IN ('code8','code6','heading4','chapter2','all','unmapped')),
    except_codes TEXT   NOT NULL DEFAULT '[]'
        CHECK (json_valid(except_codes)),
    unparsed_except_text INTEGER NOT NULL DEFAULT 0 CHECK (unparsed_except_text IN (0,1)),
    rule_group  TEXT    NOT NULL CHECK (length(trim(rule_group)) > 0)
"""

HIER_CHECK = """
    CHECK (COALESCE(
        (match_level = 'code8'    AND length(code_norm) = 8) OR
        (match_level = 'code6'    AND length(code_norm) = 6) OR
        (match_level = 'heading4' AND length(code_norm) = 4) OR
        (match_level = 'chapter2' AND length(code_norm) = 2) OR
        (match_level = 'all'      AND code_norm = '') OR
        (match_level = 'unmapped' AND code_norm IS NULL)
    , 0))
"""

RATE_COLS = """
    rate_kind   TEXT    NOT NULL
        CHECK (rate_kind IN ('percent','specific','conditional','exempt')),
    rate_pct    REAL,
    rate_specific_amount REAL,
    rate_specific_unit   TEXT,
    rate_raw    TEXT
"""

RATE_CHECK = """
    CHECK (COALESCE(
        (rate_kind = 'percent'     AND rate_pct IS NOT NULL AND rate_pct >= 0 AND rate_pct <= 100
                                   AND rate_specific_amount IS NULL) OR
        (rate_kind = 'specific'    AND rate_specific_amount IS NOT NULL AND rate_specific_amount >= 0
                                   AND rate_specific_unit IS NOT NULL AND rate_pct IS NULL) OR
        (rate_kind = 'conditional' AND rate_raw IS NOT NULL AND rate_pct IS NULL
                                   AND rate_specific_amount IS NULL) OR
        (rate_kind = 'exempt'      AND rate_pct IS NULL AND rate_specific_amount IS NULL)
    , 0))
"""

FED_RATE_CHECK = """
    CHECK (COALESCE(
        (rate_kind = 'percent'  AND rate_pct IS NOT NULL AND rate_pct >= 0 AND rate_pct <= 100
                                AND rate_specific_amount IS NULL AND rate_basis IS NOT NULL) OR
        (rate_kind = 'specific' AND rate_specific_amount IS NOT NULL AND rate_specific_amount > 0
                                AND rate_specific_unit IS NOT NULL AND rate_pct IS NULL) OR
        (rate_kind = 'compound' AND rate_pct IS NOT NULL AND rate_pct >= 0 AND rate_pct <= 100
                                AND rate_specific_amount IS NOT NULL AND rate_specific_amount > 0
                                AND rate_specific_unit IS NOT NULL AND compound_rule = 'higher_of') OR
        (rate_kind = 'exempt'   AND rate_pct IS NULL AND rate_specific_amount IS NULL)
    , 0))
"""

DDL = f"""
CREATE TABLE IF NOT EXISTS tariff_headings (
    id INTEGER PRIMARY KEY,
    fy TEXT NOT NULL CHECK (fy IN ('FY2025-26','FY2026-27')),
    heading TEXT NOT NULL CHECK (heading GLOB '[0-9][0-9].[0-9][0-9]'),
    text TEXT NOT NULL,
    {FACT_COLS},
    UNIQUE (fy, heading)
);

CREATE TABLE IF NOT EXISTS tariff_lines (
    id INTEGER PRIMARY KEY,
    fy TEXT NOT NULL CHECK (fy IN ('FY2025-26','FY2026-27')),
    code TEXT NOT NULL,               -- as printed: 0101.2100 (or 4-digit Chapter 99 code)
    code_norm TEXT NOT NULL CHECK (code_norm NOT GLOB '*[^0-9]*' AND length(code_norm) IN (4,8)),
    level INTEGER NOT NULL CHECK (level IN (4,8)),
    heading TEXT,
    description TEXT NOT NULL,
    cd_kind TEXT NOT NULL CHECK (cd_kind IN ('plain','specific','compound')),
    cd_rate REAL,                     -- percent, when cd_kind = 'plain'
    cd_specific_amount REAL,          -- rupees per unit, when cd_kind = 'specific'
    cd_specific_unit TEXT,
    cd_raw TEXT,
    rotated INTEGER NOT NULL DEFAULT 0 CHECK (rotated IN (0,1)),
    note TEXT,
    {STATUS_COL},
    {FACT_COLS},
    UNIQUE (fy, code, page),   -- Chapter 99 entries run over several pages (one row per page fragment)
    CHECK (length(code_norm) = level),
    CHECK (COALESCE(
        (cd_kind = 'plain' AND cd_rate IS NOT NULL AND cd_rate >= 0 AND cd_rate <= 100
                           AND cd_specific_amount IS NULL) OR
        (cd_kind = 'specific' AND cd_specific_amount IS NOT NULL AND cd_specific_amount >= 0
                           AND cd_specific_unit IS NOT NULL AND cd_rate IS NULL) OR
        (cd_kind = 'compound' AND cd_raw IS NOT NULL)
    , 0))
);
CREATE INDEX IF NOT EXISTS ix_tariff_lines_code ON tariff_lines (code_norm, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS sros (
    id INTEGER PRIMARY KEY,
    sro_number TEXT NOT NULL UNIQUE,  -- canonical: '1064(I)/2026'
    instrument_kind TEXT NOT NULL,    -- RD | ACD | CD | ST | IT | OTHER
    sro_date TEXT NOT NULL CHECK (date(sro_date) IS NOT NULL AND date(sro_date) = sro_date),
    supersedes TEXT,                  -- sro_number it replaces (may not be in this table)
    superseded_by TEXT,
    validity_basis TEXT NOT NULL CHECK (validity_basis IN ('clause','date_line')),
    sro_status TEXT NOT NULL CHECK (sro_status IN ('in_force','superseded','rescinded')),
    note TEXT,
    {STATUS_COL},
    {FACT_COLS}
);

CREATE TABLE IF NOT EXISTS rd_rules (
    id INTEGER PRIMARY KEY,
    sro_number TEXT NOT NULL,
    s_no TEXT NOT NULL,
    raw_pct_code TEXT NOT NULL,
    description TEXT NOT NULL,
    clause TEXT,
    issues TEXT,
    {HIER_COLS},
    {RATE_COLS},
    {STATUS_COL},
    {FACT_COLS},
    {HIER_CHECK},
    {RATE_CHECK}
);
CREATE INDEX IF NOT EXISTS ix_rd_code ON rd_rules (code_norm, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS acd_rules (
    id INTEGER PRIMARY KEY,
    sro_number TEXT NOT NULL,
    clause TEXT NOT NULL,
    slab_pct REAL,                    -- tariff CD slab the rule applies to, if slab-based
    condition_text TEXT,
    {HIER_COLS},
    {RATE_COLS},
    {STATUS_COL},
    {FACT_COLS},
    {HIER_CHECK},
    {RATE_CHECK}
);

CREATE TABLE IF NOT EXISTS sales_tax_rules (
    id INTEGER PRIMARY KEY,
    instrument TEXT NOT NULL,         -- e.g. 'Sales Tax Act 1990, Eighth Schedule' or 'SRO 1217(I)/2025'
    clause TEXT NOT NULL,             -- serial / section / clause cited
    tax_kind TEXT NOT NULL CHECK (tax_kind IN ('sales_tax','further_tax','extra_tax','withholding')),
    importer_status TEXT NOT NULL DEFAULT 'any' CHECK (importer_status IN ('any','registered','unregistered')),
    charged_on TEXT,                  -- base the tax is levied on, citing the source (see docs/duty_formula.md)
    condition_text TEXT,
    {HIER_COLS},
    {RATE_COLS},
    {STATUS_COL},
    {FACT_COLS},
    {HIER_CHECK},
    {RATE_CHECK}
);

CREATE TABLE IF NOT EXISTS income_tax_rules (
    id INTEGER PRIMARY KEY,
    instrument TEXT NOT NULL,         -- e.g. 'Income Tax Ordinance 2001, First Schedule Part II'
    clause TEXT NOT NULL,             -- section 148 + table row
    importer_status TEXT NOT NULL DEFAULT 'any',   -- filer | non_filer | company | ... as printed in the source
    importer_category TEXT,
    charged_on TEXT,
    condition_text TEXT,
    {HIER_COLS},
    {RATE_COLS},
    {STATUS_COL},
    {FACT_COLS},
    {HIER_CHECK},
    {RATE_CHECK}
);

CREATE TABLE IF NOT EXISTS fed_rules (
    id INTEGER PRIMARY KEY,
    row_id TEXT NOT NULL UNIQUE,      -- fed<year>:<table>:<serial><sub>:<code>
    fy TEXT NOT NULL CHECK (fy IN ('FY2025-26','FY2026-27')),
    schedule TEXT NOT NULL CHECK (schedule IN ('First','Third')),   -- Federal Excise Act 2005 schedule
    table_no TEXT NOT NULL,           -- 'I', 'IA' (Special Excise Duty), 'III' (First Schedule) or 'Third-I' (Third Schedule goods)
    s_no TEXT NOT NULL,               -- serial as printed: '55A', '8b'
    sub TEXT NOT NULL DEFAULT '',     -- sub-clause label '(a)' (engine-capacity / value bands)
    description TEXT NOT NULL,
    sub_desc TEXT,
    heading_raw TEXT NOT NULL DEFAULT '',   -- heading column exactly as printed ('Respective heading' = no code)
    applies_to TEXT NOT NULL CHECK (applies_to IN ('import_only','local_only','import_and_local','unclear')),
    rate_basis TEXT CHECK (rate_basis IS NULL OR rate_basis IN ('ad_valorem','retail_price')),
    rate_ref_s_no TEXT,               -- rate printed by reference to another serial (S.No 8 -> S.No 9)
    compound_rule TEXT CHECK (compound_rule IS NULL OR compound_rule = 'higher_of'),
    cc_ge INTEGER, cc_gt INTEGER, cc_le INTEGER,      -- cylinder capacity band in cc (inclusive >=, exclusive >, inclusive <=)
    usd_gt INTEGER, usd_le INTEGER,                   -- value band in USD (section 25 value), exclusive >, inclusive <=
    condition_text TEXT,
    effective_note TEXT,
    amended_by TEXT,                  -- Finance Act clause that made this row differ from the previous year (red text)
    issues TEXT NOT NULL DEFAULT '',
    {HIER_COLS},
    rate_kind TEXT NOT NULL CHECK (rate_kind IN ('percent','specific','compound','exempt')),
    rate_pct REAL,
    rate_specific_amount REAL,
    rate_specific_unit TEXT,
    rate_raw TEXT,
    {STATUS_COL},
    {FACT_COLS},
    {HIER_CHECK},
    {FED_RATE_CHECK}
);
CREATE INDEX IF NOT EXISTS ix_fed_code ON fed_rules (code_norm, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS fifth_schedule_rules (
    id INTEGER PRIMARY KEY,
    rule_id TEXT NOT NULL UNIQUE,     -- A7F-00001 (data/processed/a7_fifth_rules.csv)
    part TEXT NOT NULL,               -- I, II, III, IV, V(A), V(B), V(C), VI, VIII (Fifth Schedule to the Customs Act 1969)
    table_no TEXT NOT NULL,           -- 'main', 'A'..'E' (Part II), 'I'..'III' (Part V)
    s_no TEXT NOT NULL,               -- serial as printed: '1', '8(a)', '15A'
    sub_ref TEXT NOT NULL DEFAULT '', -- item label inside the serial: '(1).', 'i.'
    scope TEXT NOT NULL DEFAULT '',   -- plant_machinery_part_I, pharma_api, ... (see docs/store_schema.md)
    title TEXT NOT NULL DEFAULT '',   -- first row text of the serial
    group_context TEXT NOT NULL DEFAULT '',  -- group heading above the item (A) Tillage ...
    description TEXT NOT NULL DEFAULT '',
    description2 TEXT NOT NULL DEFAULT '',
    sub_items_text TEXT NOT NULL DEFAULT '', -- illustrative list that follows the item
    code_raw TEXT NOT NULL DEFAULT '',       -- PCT column exactly as read ('Respective headings' = no code)
    conditions TEXT NOT NULL DEFAULT '',     -- Conditions column text (never evaluated by the store)
    part_conditions_ref TEXT NOT NULL DEFAULT '',
    {HIER_COLS},
    rate_kind TEXT NOT NULL CHECK (rate_kind IN ('percent','fraction_of_first_schedule','nil','other','none')),
    rate_raw TEXT NOT NULL DEFAULT '',
    rate_pcts TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(rate_pcts)),   -- listed rates, ascending, e.g. ["0","3","5"]
    rate_fraction_pct REAL,           -- 50 for "50% of the prevailing rate"
    rate_note TEXT NOT NULL DEFAULT '',
    issues TEXT NOT NULL DEFAULT '',
    extraction_method TEXT NOT NULL DEFAULT '',
    {STATUS_COL},
    {FACT_COLS},
    {HIER_CHECK},
    CHECK (COALESCE(
        (rate_kind = 'percent' AND json_array_length(rate_pcts) >= 1) OR
        (rate_kind = 'fraction_of_first_schedule' AND rate_fraction_pct IS NOT NULL
                               AND rate_fraction_pct > 0 AND rate_fraction_pct <= 100) OR
        (rate_kind IN ('nil','other','none'))
    , 0))
);
CREATE INDEX IF NOT EXISTS ix_fifth_code ON fifth_schedule_rules (code_norm, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS fta_rules (
    id INTEGER PRIMARY KEY,
    row_id TEXT NOT NULL UNIQUE,      -- cpfta1640:<sr_no>:y<year_no>
    instrument TEXT NOT NULL DEFAULT 'SRO 1640(I)/2019',
    partner TEXT NOT NULL DEFAULT 'China',
    sr_no INTEGER NOT NULL,           -- Sr.No of the SRO table (1..6786)
    year_no INTEGER NOT NULL CHECK (year_no BETWEEN 1 AND 15),   -- column "Year n" (Year 1 = 1-Jan-2020)
    calendar_year INTEGER NOT NULL,
    column_date TEXT NOT NULL,        -- the date printed over the column, e.g. 1-Jan-26
    description_ocr TEXT NOT NULL DEFAULT '',   -- description as read by OCR (context only, never used for matching)
    category TEXT NOT NULL DEFAULT '',          -- constant_zero | constant_rate | A07 | A15 (fitted pattern, FBR category names)
    pattern_base_rate REAL,
    cells_read INTEGER,               -- yearly cells the OCR read on this line
    cells_agree INTEGER,              -- of those, cells that agree with the fitted pattern
    rate_source TEXT NOT NULL DEFAULT '',       -- ocr_fitted_to_taper_pattern | ocr_cells_only
    condition_text TEXT NOT NULL DEFAULT '',
    issues TEXT NOT NULL DEFAULT '',
    {HIER_COLS},
    rate_kind TEXT NOT NULL CHECK (rate_kind = 'percent'),
    rate_pct REAL NOT NULL CHECK (rate_pct >= 0 AND rate_pct <= 100),
    rate_raw TEXT,
    {STATUS_COL},
    {FACT_COLS},
    {HIER_CHECK},
    CHECK (match_level = 'code8')
);
CREATE INDEX IF NOT EXISTS ix_fta_code ON fta_rules (code_norm, valid_from, valid_to);

CREATE TABLE IF NOT EXISTS legal_notes (
    id INTEGER PRIMARY KEY,
    note_kind TEXT NOT NULL CHECK (note_kind IN ('general_rule','section_note','chapter_note','subheading_note')),
    scope TEXT NOT NULL,              -- 'General', 'Section XVI', 'Chapter 87', ...
    note_no TEXT NOT NULL,
    hs_edition TEXT NOT NULL DEFAULT 'HS2022',
    text TEXT NOT NULL,
    table_json TEXT CHECK (table_json IS NULL OR json_valid(table_json)),  -- structured table of the note; `text` keeps the flattened original
    {STATUS_COL},
    {FACT_COLS},
    UNIQUE (note_kind, scope, note_no, valid_from)
);
"""
