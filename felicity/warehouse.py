"""Build the local warehouse: schema, raw load, staging, marts.

DuckDB runs locally. The SQL files are written to run on Postgres too; the only
DuckDB-specific line is the COPY path handling noted in docs/dialect_notes.md.
"""
from pathlib import Path

import duckdb

from . import config

RAW_TABLES = ["agencies", "branches", "branch_hours", "conversations", "messages",
              "outcomes", "crm_leads", "crm_events"]
REF_TABLES = ["uk_clock_changes", "bank_holidays", "reporting_window"]


def run_sql_file(con, path: Path) -> None:
    con.execute(path.read_text())


def build(db_path: Path = config.DB_PATH, raw_dir: Path = config.RAW_DIR) -> duckdb.DuckDBPyConnection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    run_sql_file(con, config.SQL_DIR / "00_schema.sql")
    for schema, tables in (("raw", RAW_TABLES), ("ref", REF_TABLES)):
        for t in tables:
            # Same statement works in Postgres (server-side file) or as psql \copy.
            con.execute(f"COPY {schema}.{t} FROM '{raw_dir / (t + '.csv')}' (FORMAT csv, HEADER true)")
    for layer in ("staging", "marts"):
        for f in sorted((config.SQL_DIR / layer).glob("*.sql")):
            run_sql_file(con, f)
    return con


def rows(con, sql: str) -> list[dict]:
    cur = con.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]
