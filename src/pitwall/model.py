import numpy as np
from sklearn.base import BaseEstimator, RegressorMixin, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LinearRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder

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


def build_pipeline(include_race_lap: bool, wear_by_pair: bool = False, fuel_column: str = "lap_number") -> Pipeline:
    '''
    Unfitted linear model of delta from compound, tyre age and optionally race lap.

    include_race_lap: if True, fuel_column is used as a feature (fuel proxy)
    wear_by_pair: if True, each compound@circuit pair gets its own tyre-age
        column (PairAgeColumns) instead of one shared "tyre_age" column
    fuel_column: name of the fuel-proxy column, "lap_number" (default) or
        "race_fraction" (see features.add_race_fraction)

    returns: sklearn Pipeline that expects a DataFrame with "compound" (str)
        and "tyre_age" (int), plus fuel_column when include_race_lap
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
        num_cols.append(fuel_column)
    
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


class PooledWearModel(BaseEstimator, RegressorMixin):
    '''
    One shared wear rate plus a per compound@circuit adjustment that is pulled
    toward 0 (partial pooling), all fitted together.

    Columns: one-hot compound (these act as the intercept), tyre_age (the
    shared rate), fuel_column, and one "age:<pair>" column per pair
    (PairAgeColumns, the adjustments). fit solves the ridge equations
    (XᵀX + alpha·D) b = Xᵀy, where D is 1 for the adjustment columns and 0
    for the rest, so only the adjustments are penalised and the fuel term,
    compound offsets and shared rate are free to move with them.
    predict: X times the fitted coefficients.

    alpha: penalty strength, must be > 0. Near 0 gives each pair its own rate
        (Model C); very large forces every adjustment to 0 (Model B). A pair
        with few laps is pulled toward the shared rate more than a pair with
        many.
    fuel_column: fuel-proxy column, "race_fraction" (default) or "lap_number"

    Expects a DataFrame with "compound", "circuit", "tyre_age" and
    fuel_column. fit raises ValueError if alpha <= 0. Predicting raises
    ValueError for a compound or a compound@circuit pair not seen during fitting.
    '''

    def __init__(self, alpha: float = 1.0, fuel_column: str = "race_fraction"):
        self.alpha = alpha
        self.fuel_column = fuel_column

    def fit(self, X, y):
        # tyre_age equals the sum of the age:pair columns, so the fit needs alpha > 0 to have one answer.
        if self.alpha <= 0:
            raise ValueError(f"alpha must be > 0, got {self.alpha}")
        self.columns_ = ColumnTransformer(
            transformers=[
                ("cat", OneHotEncoder(handle_unknown='error', sparse_output=False), ['compound']),
                ("pass", "passthrough", ['tyre_age', self.fuel_column]),
                ("wear", PairAgeColumns(), ['compound', 'circuit', 'tyre_age']),
            ],
            remainder="drop",
        )
        features = np.asarray(self.columns_.fit_transform(X), dtype=float)
        names = self.columns_.get_feature_names_out()
        penalised = np.array([name.startswith("wear__") for name in names], dtype=float)
        lhs = features.T @ features + self.alpha * np.diag(penalised)
        self.coef_ = np.linalg.solve(lhs, features.T @ np.asarray(y, dtype=float))
        return self

    def predict(self, X):
        return np.asarray(self.columns_.transform(X), dtype=float) @ self.coef_

    def pair_adjustments(self) -> dict[str, float]:
        '''Fitted adjustment to the shared wear rate per pair, in seconds per lap of tyre age.'''
        names = self.columns_.get_feature_names_out()
        return {name.removeprefix("wear__age:"): float(c)
                for name, c in zip(names, self.coef_) if name.startswith("wear__")}
