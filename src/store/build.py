"""Build the legal store: python -m src.store.build [--db PATH]"""
import argparse
import json

from .db import DEFAULT_DB_PATH, connect, init_db
from .loaders import PROC, fifth_rows, legal_notes_rows, load_instruments, load_rd, load_rd_used_vehicles, load_sros, load_table_file, load_tariff


def build(db_path=DEFAULT_DB_PATH) -> dict:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = init_db(connect(db_path))
    report = {"sros": load_sros(conn)}
    for key in ("tariff_2026_27", "tariff_2025_26"):
        report[key] = load_tariff(conn, key)
    report["rd_1064"] = load_rd(conn, "sro_1064_rd", "1064(I)/2026")
    report["rd_1152"] = load_rd(conn, "sro_1152_rd", "1152(I)/2025")
    report["rd_used_vehicles"] = load_rd_used_vehicles(conn)
    report["a3_instruments"] = load_instruments(conn)
    report["acd_rules"] = load_table_file(conn, "acd_rules", PROC / "a3_acd_rules.csv")
    report["sales_tax_rules"] = load_table_file(conn, "sales_tax_rules", PROC / "a3_sales_tax_rules.csv")
    report["income_tax_rules"] = load_table_file(conn, "income_tax_rules", PROC / "a3_income_tax_rules.csv")
    report["fed_rules"] = load_table_file(conn, "fed_rules", PROC / "a6_fed_rules.csv")
    mapped = PROC / "a6_fed_rules_mapped.json"      # derived by src.ingest.a6_fed_mapping from a6_fed_mapping.csv (description match, owner has not verified)
    report["fed_rules_mapped"] = load_table_file(conn, "fed_rules", mapped) if mapped.exists() else 0
    report["fifth_schedule_rules"] = 0
    for csv_name, store_name in (("a7_fifth_rules.csv", "a7_fifth_rules_store.json"), ("a7_fifth_rules_2025_26.csv", "a7_fifth_rules_2025_26_store.json")):
        if (PROC / csv_name).exists():      # mapped to the table contract; gitignored (rebuilt here), the CSV is the audited file
            (PROC / store_name).write_text(json.dumps(fifth_rows(PROC / csv_name), indent=1, ensure_ascii=False), encoding="utf-8")
            report["fifth_schedule_rules"] += load_table_file(conn, "fifth_schedule_rules", PROC / store_name)
    notes = PROC / "legal_notes_store.json"      # derived from legal_notes.json (A4), kept in git so the mapping is auditable
    notes.write_text(json.dumps(legal_notes_rows(), indent=1, ensure_ascii=False), encoding="utf-8")
    report["legal_notes"] = load_table_file(conn, "legal_notes", notes)
    conn.close()
    return report


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(DEFAULT_DB_PATH))
    from pathlib import Path
    a = ap.parse_args()
    print(json.dumps(build(Path(a.db)), indent=1))
