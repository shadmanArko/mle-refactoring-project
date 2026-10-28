"""The reusable pipelines: preprocessing alone, and preprocessing plus the model."""

from sklearn.compose import TransformedTargetRegressor
from sklearn.linear_model import ElasticNet
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import (
    FunctionTransformer,
    PolynomialFeatures,
    StandardScaler,
)

from kc_house.cleaning import clean
from kc_house.config import ELASTIC_NET_ALPHA, ELASTIC_NET_L1_RATIO
from kc_house.features import WaterDistance, add_center_distance, select_model_features


def build_preprocessing() -> Pipeline:
    """Raw house columns in, the model's feature frame out.

    Fit on training rows only: ``WaterDistance`` learns from what it is fitted on.
    """
    return Pipeline(
        [
            ("clean", FunctionTransformer(clean)),
            ("center_distance", FunctionTransformer(add_center_distance)),
            ("water_distance", WaterDistance()),
            ("select", FunctionTransformer(select_model_features)),
        ]
    )


def build_model_pipeline(
    alpha: float = ELASTIC_NET_ALPHA, l1_ratio: float = ELASTIC_NET_L1_RATIO
) -> Pipeline:
    """Preprocessing, polynomial features, scaling and ElasticNet on price."""
    return Pipeline(
        [
            ("preprocess", build_preprocessing()),
            ("polynomial", PolynomialFeatures(2, include_bias=False)),
            ("scaler", StandardScaler()),
            (
                "model",
                TransformedTargetRegressor(
                    regressor=ElasticNet(
                        alpha=alpha,
                        l1_ratio=l1_ratio,
                        max_iter=5000,
                        tol=1e-4,
                        precompute=True,
                    ),
                    transformer=StandardScaler(),
                ),
            ),
        ]
    )
