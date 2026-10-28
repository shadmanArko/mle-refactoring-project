"""Loads the six-question estimator once and turns answers into a price range."""

import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import skops.io as sio
from sklearn.pipeline import Pipeline

from kc_house.config import ESTIMATE_INPUTS


class UnknownZipcodeError(ValueError):
    """The zip code is not one the model was trained on."""


@dataclass(frozen=True)
class Estimate:
    price: int
    low: int
    high: int


def _round_to_thousand(value: float) -> int:
    return int(round(value, -3))


class EstimatorService:
    """Wraps the saved estimator and the facts the API reports about it."""

    def __init__(self, model_dir: Path) -> None:
        metrics_path = model_dir / "metrics.json"
        model_path = model_dir / "estimator.skops"
        for path in (metrics_path, model_path):
            if not path.exists():
                raise FileNotFoundError(
                    f"{path} not found. Train first: `uv run kc-train`."
                )
        report = json.loads(metrics_path.read_text())
        trusted = report["skops_trusted_types"]["estimator"]
        self._model: Pipeline = sio.load(model_path, trusted=trusted)
        self._zipcodes = [
            int(code) for code in self._model.named_steps["defaults"].zipcodes_
        ]
        self._interval = report["estimator"]["interval"]
        metadata = report["metadata"]
        self.info = {
            "model_version": f"{metadata['git_sha'][:7]}-{metadata['trained_at'][:10]}",
            "trained_at": metadata["trained_at"],
            "sale_dates": metadata["sale_dates"],
            "r2": report["estimator"]["test_metrics"]["r2"],
            "typical_error_pct": report["estimator"]["test_metrics"][
                "median_abs_pct_error"
            ],
            "range_coverage": self._interval["coverage"],
        }

    @property
    def zipcodes(self) -> list[int]:
        return self._zipcodes

    def require_known_zipcode(self, zipcode: int) -> None:
        if zipcode not in self._zipcodes:
            raise UnknownZipcodeError(
                f"Zip code {zipcode} is not covered; see /api/zipcodes for the list."
            )

    def estimate(self, answers: dict) -> Estimate:
        self.require_known_zipcode(answers["zipcode"])
        frame = pd.DataFrame([answers])[ESTIMATE_INPUTS]
        price = float(self._model.predict(frame)[0])
        return Estimate(
            price=_round_to_thousand(price),
            low=_round_to_thousand(price * self._interval["low_ratio"]),
            high=_round_to_thousand(price * self._interval["high_ratio"]),
        )
