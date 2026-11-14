from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder
from sklearn.linear_model import LinearRegression
from sklearn.base import BaseEstimator, TransformerMixin

from pitwall.features import pair_age_columns


class PairAgeColumns(BaseEstimator, TransformerMixin):
    '''
    Pipeline step that gives each compound@circuit pair its own tyre-age column.

    fit learns the pairs seen in the training data. transform builds one
    "age:<compound>@<circuit>" column per learned pair (see pair_age_columns),
    in the same order every time, so 2025 rows get the columns learned from
    2024. Expects a DataFrame with "compound", "circuit" and "tyre_age".
    transform raises ValueError for a pair not seen during fit.
    '''

    def fit(self, X, y=None):
        pair = X["compound"] + "@" + X["circuit"]
        self.pairs_ = sorted(pair.unique())
        return self

    def transform(self, X):
        return pair_age_columns(X, self.pairs_)

    def get_feature_names_out(self, input_features=None):
        return ["age:" + p for p in self.pairs_]


def build_pipeline(include_race_lap: bool, wear_by_pair: bool = False) -> Pipeline:
    '''
    Unfitted linear model of delta from compound, tyre age and optionally race lap.

    include_race_lap: if True, "lap_number" is used as a feature (fuel proxy)
    wear_by_pair: if True, each compound@circuit pair gets its own tyre-age
        column (PairAgeColumns) instead of one shared "tyre_age" column

    returns: sklearn Pipeline that expects a DataFrame with "compound" (str)
        and "tyre_age" (int), plus "lap_number" (int) when include_race_lap
        is True and "circuit" (str) when wear_by_pair is True. Compound is
        one-hot encoded, the numeric columns pass through unchanged, and
        every other column is dropped.

    Fitting raises ValueError if a required column is missing. Predicting
    raises ValueError for a compound, or with wear_by_pair a compound@circuit
    pair, not seen during fitting.
    '''
    cat_cols = ['compound']
    num_cols = []
    if not wear_by_pair:
        num_cols.append('tyre_age')
    if include_race_lap:
        num_cols.append('lap_number')
    
    transformers = [
        ("cat", OneHotEncoder(handle_unknown='error'), cat_cols),
        ("pass", "passthrough", num_cols)
    ]
    if wear_by_pair:
        transformers.append(("wear", PairAgeColumns(), ['compound', 'circuit', 'tyre_age']))
    preprocessor = ColumnTransformer(
        transformers=transformers,
        remainder="drop", 
    )

    full_pipeline = Pipeline([
        ("preprocessor", preprocessor),
        ("regressor", LinearRegression()),
    ])

    return full_pipeline


