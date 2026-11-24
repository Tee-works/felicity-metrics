"""Run settings. Fixed dates and a fixed seed so every run gives the same numbers."""
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
TRUTH_DIR = DATA_DIR / "truth"
DB_PATH = DATA_DIR / "felicity.duckdb"
SQL_DIR = ROOT / "sql"
REPORTS_DIR = ROOT / "reports"
QUALITY_DIR = ROOT / "quality"

SEED = 20261125

# Reporting window in UK local time. It covers the 31 Aug bank holiday and the
# BST to GMT change on 25 Oct 2026, so both timezone rules get exercised.
WINDOW_START_LOCAL = datetime(2026, 8, 3)
WINDOW_END_LOCAL = datetime(2026, 11, 16)  # exclusive

# "Now" for freshness checks (UTC).
AS_OF_UTC = datetime(2026, 11, 16, 6, 0)
FRESHNESS_SLA_HOURS = 26

# The synthetic Street CRM feed stops here, so the freshness check has something to find.
STREET_FEED_STOPPED_UTC = datetime(2026, 11, 12, 14, 0)
