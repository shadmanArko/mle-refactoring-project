"""API fixtures: a small but real saved estimator, and a client wired to SQLite."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pandas as pd
import pytest
import skops.io as sio
from fastapi.testclient import TestClient
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.pipeline import Pipeline

from kc_house.api.main import create_app
from kc_house.api.settings import Settings
from kc_house.cleaning import drop_implausible_rows
from kc_house.estimator import build_estimator
from kc_house.pipeline import build_preprocessing

API_KEY = "test-key"


@pytest.fixture(scope="session")
def artifacts_dir(raw_data: pd.DataFrame, tmp_path_factory) -> Iterator:
    """Train a quick estimator and save it exactly the way ``kc-train`` does."""
    directory = tmp_path_factory.mktemp("artifacts")
    rows = drop_implausible_rows(raw_data).sample(8000, random_state=0)
    full_model = Pipeline(
        [
            ("preprocess", build_preprocessing()),
            ("model", HistGradientBoostingRegressor(max_iter=40, random_state=0)),
        ]
    )
    estimator = build_estimator(full_model).fit(
        rows.drop(columns=["price"]), rows["price"]
    )
    sio.dump(estimator, directory / "estimator.skops")
    trusted = sorted(sio.get_untrusted_types(file=directory / "estimator.skops"))
    report = {
        "metadata": {
            "git_sha": "abc1234def",
            "trained_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "sale_dates": ["2014-05-02", "2015-05-27"],
        },
        "estimator": {
            "test_metrics": {"r2": 0.84, "median_abs_pct_error": 10.5},
            "interval": {"coverage": 0.8, "low_ratio": 0.85, "high_ratio": 1.15},
        },
        "skops_trusted_types": {"estimator": trusted},
    }
    (directory / "metrics.json").write_text(json.dumps(report))
    yield directory


@pytest.fixture
def house() -> dict:
    return {
        "bedrooms": 3,
        "bathrooms": 2.0,
        "sqft_living": 1800,
        "grade": 7,
        "zipcode": 98103,
    }


@pytest.fixture
def make_settings(artifacts_dir, tmp_path):
    """Build Settings pointing at the test model and a throwaway SQLite file."""

    def build(**overrides) -> Settings:
        values = {
            "database_url": f"sqlite:///{tmp_path}/test.db",
            "model_dir": artifacts_dir,
            "api_key": API_KEY,
        } | overrides
        return Settings(_env_file=None, **values)  # pyright: ignore[reportCallIssue]

    return build


@pytest.fixture
def client(make_settings) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings())) as test_client:
        yield test_client


@pytest.fixture
def auth() -> dict[str, str]:
    return {"X-API-Key": API_KEY}
