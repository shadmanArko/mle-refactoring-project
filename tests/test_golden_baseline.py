"""The frozen notebook baseline must stay readable and self-consistent.

Phase 1 adds the parity test that compares the refactored pipeline to it.
"""

import json
from pathlib import Path

import pandas as pd

GOLDEN = Path(__file__).parent / "golden"


def test_baseline_metrics_are_complete() -> None:
    metrics = json.loads((GOLDEN / "baseline_metrics.json").read_text())

    assert metrics["clean_shape"] == [21596, 25]
    assert metrics["x_train_shape"][0] + metrics["x_test_shape"][0] == 21596
    assert 0.80 < metrics["elastic_test_r2"] < 0.90


def test_clean_frame_matches_recorded_shape() -> None:
    metrics = json.loads((GOLDEN / "baseline_metrics.json").read_text())
    frame = pd.read_csv(GOLDEN / "clean_frame.csv.gz", index_col=0)

    assert list(frame.shape) == metrics["clean_shape"]
    assert list(frame.columns) == metrics["clean_columns"]
    assert frame[["view", "waterfront", "last_known_change"]].notna().to_numpy().all()
