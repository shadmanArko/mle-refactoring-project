import json

import pandas as pd
import pytest
import skops.io as sio

from kc_house import train
from kc_house.config import ESTIMATE_INPUTS
from kc_house.data import make_training_split
from kc_house.train import BelowFloorError, run_training, tune_reference_model


@pytest.fixture(scope="module")
def sample_csv(raw_data, tmp_path_factory):
    """A 5,000-row sample keeps the training run fast."""
    path = tmp_path_factory.mktemp("data") / "sample.csv"
    raw_data.sample(5000, random_state=0).to_csv(path, index=False)
    return path


QUICK_SEARCH_SPACE = {"model__max_iter": [20], "model__learning_rate": [0.1]}


@pytest.fixture(autouse=True)
def quick_search_space(monkeypatch):
    """These tests check the plumbing, so boosting needs only a handful of trees."""
    monkeypatch.setattr(train, "PRODUCTION_SEARCH_SPACE", QUICK_SEARCH_SPACE)


@pytest.fixture(scope="module")
def trained(sample_csv, tmp_path_factory):
    out = tmp_path_factory.mktemp("artifacts")
    # The floors are about the real data; a small sample only needs to run end to end.
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(train, "PRODUCTION_SEARCH_SPACE", QUICK_SEARCH_SPACE)
        patch.setattr(train, "MIN_ACCEPTABLE_R2", 0.0)
        patch.setattr(train, "MIN_ACCEPTABLE_R2_ESTIMATE", 0.0)
        report = run_training(
            sample_csv,
            out,
            cv=2,
            compare_models=True,
            search_iterations=1,
            card_path=out / "card.md",
        )
    return out, report


def test_training_writes_both_models_metrics_and_card(trained):
    out, _ = trained

    assert (out / "model.skops").exists()
    assert (out / "estimator.skops").exists()
    assert (out / "metrics.json").exists()
    assert (out / "card.md").read_text().startswith("# Model card")


def test_saved_models_load_with_their_allow_lists_and_predict(trained, sample_csv):
    out, report = trained
    rows = pd.read_csv(sample_csv).drop(columns=["price"]).head(3)
    trusted = report["skops_trusted_types"]

    full = sio.load(out / "model.skops", trusted=trusted["model"])
    estimator = sio.load(out / "estimator.skops", trusted=trusted["estimator"])

    assert full.predict(rows).shape == (3,)
    assert estimator.predict(rows[ESTIMATE_INPUTS]).shape == (3,)


def test_metrics_record_provenance_and_baselines_scored_first(trained):
    out, _ = trained

    saved = json.loads((out / "metrics.json").read_text())

    assert len(saved["metadata"]["data_sha256"]) == 64
    assert saved["metadata"]["random_state"] == 42
    roles = [row["role"] for row in saved["comparison"]]
    assert roles[:2] == ["baseline", "baseline"]
    assert roles[-1] == "production"
    assert "reference" in roles
    names = {row["name"] for row in saved["comparison"]}
    assert {"ridge", "random_forest", "elastic_net_poly"} <= names
    assert set(saved["split_robustness"]) == {
        "random (notebook)",
        "grouped by house id",
        "temporal (train past, test future)",
    }
    assert saved["estimator"]["inputs"] == ESTIMATE_INPUTS
    interval = saved["estimator"]["interval"]
    assert 0 < interval["low_ratio"] < 1 < interval["high_ratio"]
    assert 0 <= interval["test_coverage"] <= 1


@pytest.mark.parametrize("floor", ["MIN_ACCEPTABLE_R2", "MIN_ACCEPTABLE_R2_ESTIMATE"])
def test_a_model_below_its_floor_is_not_saved(sample_csv, tmp_path, monkeypatch, floor):
    monkeypatch.setattr(train, "MIN_ACCEPTABLE_R2", 0.0)
    monkeypatch.setattr(train, "MIN_ACCEPTABLE_R2_ESTIMATE", 0.0)
    monkeypatch.setattr(train, floor, 0.999)

    with pytest.raises(BelowFloorError):
        run_training(
            sample_csv, tmp_path, cv=2, compare_models=False, search_iterations=1
        )

    assert not (tmp_path / "model.skops").exists()
    assert not (tmp_path / "estimator.skops").exists()


def test_cli_returns_nonzero_when_the_floor_is_missed(
    sample_csv, tmp_path, monkeypatch
):
    monkeypatch.setattr(train, "MIN_ACCEPTABLE_R2", 0.999)

    arguments = ["--data", str(sample_csv), "--out", str(tmp_path)]
    code = train.main([*arguments, "--cv", "2", "--search-iterations", "1"])

    assert code == 1


def test_cli_succeeds_and_prints_the_test_metrics(
    sample_csv, tmp_path, monkeypatch, capsys
):
    monkeypatch.setattr(train, "MIN_ACCEPTABLE_R2", 0.0)
    monkeypatch.setattr(train, "MIN_ACCEPTABLE_R2_ESTIMATE", 0.0)
    arguments = ["--data", str(sample_csv), "--out", str(tmp_path)]

    code = train.main(
        [*arguments, "--cv", "2", "--search-iterations", "1", "--skip-comparison"]
    )

    assert code == 0
    assert '"r2"' in capsys.readouterr().out


def test_reference_grid_search_finds_the_notebooks_hyperparameters(raw_data):
    """Same grid, same data: the refactor reaches the notebook's tuned settings."""
    X_train, _, y_train, _ = make_training_split(raw_data)

    search = tune_reference_model(X_train, y_train)

    assert search.best_params_ == {
        "model__regressor__alpha": 0.01,
        "model__regressor__l1_ratio": 0.2,
    }
    assert search.best_score_ == pytest.approx(0.8266, abs=0.01)
