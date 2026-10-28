"""Candidate models compared during training, from baselines to boosted trees."""

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from kc_house.config import RANDOM_STATE
from kc_house.pipeline import build_model_pipeline, build_preprocessing


def build_baselines() -> dict[str, Pipeline]:
    """What any model must beat to justify its complexity."""
    return {
        "mean_baseline": Pipeline([("model", DummyRegressor(strategy="mean"))]),
        "grade_only_linear": Pipeline(
            [
                ("pick", ColumnTransformer([("grade", "passthrough", ["grade"])])),
                ("model", LinearRegression()),
            ]
        ),
    }


def build_candidates() -> dict[str, Pipeline]:
    """Alternative families, every one with leak-free preprocessing in front."""
    return {
        "ridge": Pipeline(
            [
                ("preprocess", build_preprocessing()),
                ("scaler", StandardScaler()),
                ("model", Ridge(alpha=1.0)),
            ]
        ),
        "random_forest": Pipeline(
            [
                ("preprocess", build_preprocessing()),
                (
                    "model",
                    RandomForestRegressor(
                        n_estimators=200,
                        min_samples_leaf=2,
                        n_jobs=-1,
                        random_state=RANDOM_STATE,
                    ),
                ),
            ]
        ),
        "hist_gradient_boosting": Pipeline(
            [
                ("preprocess", build_preprocessing()),
                (
                    "model",
                    HistGradientBoostingRegressor(
                        learning_rate=0.1, max_iter=300, random_state=RANDOM_STATE
                    ),
                ),
            ]
        ),
    }


def build_production_model() -> Pipeline:
    """The notebook's model: polynomial features and ElasticNet."""
    return build_model_pipeline()
