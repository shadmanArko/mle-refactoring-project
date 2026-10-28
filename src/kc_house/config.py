"""Constants shared by cleaning, features and the model pipeline."""

import math
from pathlib import Path

DEFAULT_DATA_PATH = Path("data/King_County_House_prices_dataset.csv")

TARGET = "price"
RANDOM_STATE = 42
TEST_SIZE = 0.3

# A sale with this many bedrooms (and 2 bathrooms) is a data-entry error.
IMPLAUSIBLE_BEDROOMS = 33

# "Centre of wealth" reference point used by the distance feature.
CENTER_LAT = 47.62774
CENTER_LONG = -122.24194
# The notebook corrects longitude with the cosine of this latitude, which is
# slightly different from CENTER_LAT. Kept as-is so results match the notebook.
CENTER_COS_LAT = 47.6219

EARTH_RADIUS_KM = 6378
KM_PER_DEGREE = 2 * math.pi * EARTH_RADIUS_KM / 360

# Columns the model sees, in the notebook's order (identifier excluded).
MODEL_FEATURES = [
    "bedrooms",
    "bathrooms",
    "sqft_living",
    "sqft_lot",
    "floors",
    "waterfront",
    "view",
    "condition",
    "grade",
    "sqft_above",
    "sqft_basement",
    "zipcode",
    "lat",
    "long",
    "sqft_living15",
    "sqft_lot15",
    "last_known_change",
    "center_distance",
    "water_distance",
]

# Stopping condition: a model below this held-out R^2 is not shipped.
# The notebook reaches ~0.84; the grade-only baseline reaches ~0.43.
MIN_ACCEPTABLE_R2 = 0.80

DEFAULT_ARTIFACTS_DIR = Path("artifacts")

# Hyperparameters chosen by the notebook's grid search.
ELASTIC_NET_ALPHA = 0.01
ELASTIC_NET_L1_RATIO = 0.2
