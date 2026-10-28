"""Models compared during training: baselines, the notebook's model, the champion."""

from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyRegressor
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor
from sklearn.linear_model import LinearRegression, Ridge
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from kc_house.config import RANDOM_STATE
from kc_house.pipeline import build_model_pipeline, build_preprocessing

# Searched at random (a grid over these would be 486 combinations).
PRODUCTION_SEARCH_SPACE = {
    "model__learning_rate": [0.03, 0.05, 0.1],
    "model__max_iter": [300, 600, 1000],
    "model__max_leaf_nodes": [15, 31, 63],
    "model__min_samples_leaf": [10, 20, 40],
    "model__l2_regularization": [0.0, 0.1, 1.0],
    # "gamma" models prices as multiplicative errors, which suits skewed prices.
    "model__loss": ["squared_error", "gamma"],
}


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


def build_reference_model() -> Pipeline:
    """The notebook's polynomial ElasticNet, kept as the documented reference."""
    return build_model_pipeline()


def build_candidates() -> dict[str, Pipeline]:
    """Other families, every one with leak-free preprocessing in front."""
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
    }


def build_production_model() -> Pipeline:
    """The champion: gradient-boosted trees behind the shared preprocessing."""
    return Pipeline(
        [
            ("preprocess", build_preprocessing()),
            ("model", HistGradientBoostingRegressor(random_state=RANDOM_STATE)),
        ]
    )
