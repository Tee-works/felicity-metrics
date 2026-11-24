import csv
import re

from felicity import generate
from felicity.generate import is_bst, local_to_utc, utc_to_local
from datetime import datetime


def test_same_seed_same_data(tmp_path, built):
    again = generate.generate(out_dir=tmp_path / "raw", truth_dir=tmp_path / "truth")
    assert again == built["counts"]
    assert (tmp_path / "raw" / "messages.csv").read_text() == (built["raw"] / "messages.csv").read_text()


def test_contact_details_are_obviously_synthetic(built):
    with open(built["raw"] / "crm_leads.csv") as f:
        leads = list(csv.DictReader(f))
    assert leads
    assert all(l["contact_email"].endswith("@example.com") for l in leads)
    # Ofcom drama range only
    assert all(re.sub(r"\D", "", l["contact_phone"]).endswith(l["contact_phone"][-3:]) and "7700" in l["contact_phone"]
               and "900" in l["contact_phone"] for l in leads)


def test_uk_clock_rules():
    assert is_bst(datetime(2026, 7, 1, 12))
    assert not is_bst(datetime(2026, 12, 1, 12))
    # 25 Oct 2026: clocks go back at 01:00 UTC
    assert is_bst(datetime(2026, 10, 25, 0, 59))
    assert not is_bst(datetime(2026, 10, 25, 1, 0))
    assert local_to_utc(datetime(2026, 8, 3, 9, 0)) == datetime(2026, 8, 3, 8, 0)
    assert local_to_utc(datetime(2026, 11, 3, 9, 0)) == datetime(2026, 11, 3, 9, 0)
    assert utc_to_local(datetime(2026, 8, 3, 8, 0)) == datetime(2026, 8, 3, 9, 0)
