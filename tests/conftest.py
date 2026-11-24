import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from felicity import generate, warehouse  # noqa: E402


@pytest.fixture(scope="session")
def built(tmp_path_factory):
    """Generate the synthetic data and build the warehouse once, in a temp folder."""
    root = tmp_path_factory.mktemp("run")
    raw, truth = root / "raw", root / "truth"
    counts = generate.generate(out_dir=raw, truth_dir=truth)
    con = warehouse.build(db_path=root / "test.duckdb", raw_dir=raw)
    return {"con": con, "counts": counts, "raw": raw, "truth": truth}


@pytest.fixture(scope="session")
def con(built):
    return built["con"]
