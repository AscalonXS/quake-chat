"""
train_aftershock_ai.py - Train a Neural Network + Gradient Boosted Ensemble on ALL rows of data/catalog.csv
to forecast damaging aftershock sequences (M4.5+, M5.0+, M6.0+, M7.0+) over 24h and 7d.

Run:  python train_aftershock_ai.py
"""
import os
import pickle
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.metrics import mean_absolute_error
from sklearn.neural_network import MLPRegressor
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

CATALOG_PATH = "data/catalog.csv"
MODEL_OUT = "models/aftershock_ai.pkl"

TARGETS = [
    "24h_M4.5+", "24h_M5+", "24h_M6+", "24h_M7+",
    "7d_M4.5+",  "7d_M5+",  "7d_M6+",  "7d_M7+",
]

def _haversine_km(lat1, lon1, lat2, lon2):
    la1, lo1, la2, lo2 = map(np.radians, (lat1, lon1, lat2, lon2))
    a = np.sin((la2 - la1) / 2) ** 2 + np.cos(la1) * np.cos(la2) * np.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371 * np.arcsin(np.sqrt(a))

def build_all_sequences(df):
    """Extract features and M4.5+ to M7.0+ aftershock targets for EVERY valid row in catalog.csv."""
    df = df.copy()
    df["dt"] = pd.to_datetime(df["time_utc"], utc=True, errors="coerce")
    df = df.dropna(subset=["dt", "lat", "lon", "mag"]).sort_values("dt").reset_index(drop=True)

    epoch = pd.Timestamp("1970-01-01", tz="UTC")
    times_s = (df["dt"] - epoch).dt.total_seconds().values

    lats = df["lat"].values.astype(float)
    lons = df["lon"].values.astype(float)
    depths = df["depth_km"].fillna(10.0).values.astype(float)
    mags = df["mag"].values.astype(float)

    t_min, t_max = times_s[0] + 30 * 86400, times_s[-1] - 7 * 86400
    valid_idxs = np.where((times_s >= t_min) & (times_s <= t_max))[0]

    pre30_starts = np.searchsorted(times_s, times_s[valid_idxs] - 30 * 86400)
    post7_ends = np.searchsorted(times_s, times_s[valid_idxs] + 7 * 86400, side="right")

    n = len(valid_idxs)
    X = np.empty((n, 6), dtype=float)
    Y = np.empty((n, len(TARGETS)), dtype=float)

    for k, (idx, i_pre30, i_post7) in enumerate(zip(valid_idxs, pre30_starts, post7_ends)):
        t0 = times_s[idx]
        m0 = mags[idx]
        d0 = depths[idx]
        la0, lo0 = lats[idx], lons[idx]

        # Pre-event seismicity within 250 km
        if idx > i_pre30:
            dist_pre = _haversine_km(la0, lo0, lats[i_pre30:idx], lons[i_pre30:idx])
            dt_pre = t0 - times_s[i_pre30:idx]
            near_250 = dist_pre <= 250.0
            bg_30d = int(np.sum(near_250))
            bg_24h = int(np.sum(near_250 & (dt_pre <= 86400)))
            has_larger_7d = float(np.any((dist_pre <= 100.0) & (dt_pre <= 7 * 86400) & (mags[i_pre30:idx] >= m0)))
        else:
            bg_30d = 0
            bg_24h = 0
            has_larger_7d = 0.0

        # Post-event observed aftershocks within 150 km over 24h and 7d (wider radius captures large fault zones)
        if i_post7 > idx + 1:
            sl = slice(idx + 1, i_post7)
            dist_post = _haversine_km(la0, lo0, lats[sl], lons[sl])
            dt_post = times_s[sl] - t0
            m_post = mags[sl]

            near_7d = dist_post <= 150.0
            near_24h = near_7d & (dt_post <= 86400)

            counts = [
                np.sum(near_24h & (m_post >= 4.5)),
                np.sum(near_24h & (m_post >= 5.0)),
                np.sum(near_24h & (m_post >= 6.0)),
                np.sum(near_24h & (m_post >= 7.0)),
                np.sum(near_7d & (m_post >= 4.5)),
                np.sum(near_7d & (m_post >= 5.0)),
                np.sum(near_7d & (m_post >= 6.0)),
                np.sum(near_7d & (m_post >= 7.0)),
            ]
        else:
            counts = [0] * len(TARGETS)

        X[k] = [m0, d0, abs(la0), np.log1p(bg_30d), np.log1p(bg_24h), has_larger_7d]
        Y[k] = np.log1p(counts)

    return X, Y

def _make_pair():
    gbdt = HistGradientBoostingRegressor(max_depth=6, learning_rate=0.05, max_iter=250, random_state=42)
    mlp = make_pipeline(
        StandardScaler(),
        MLPRegressor(hidden_layer_sizes=(64, 32), activation="relu", max_iter=300, early_stopping=True, random_state=42),
    )
    return gbdt, mlp

def train():
    print(f"Loading {CATALOG_PATH}...")
    df = pd.read_csv(CATALOG_PATH)
    X, Y = build_all_sequences(df)
    print(f"Built training sequences from {len(X):,} rows in catalog.csv.")

    # Phase 1: Chronological 80/20 split to evaluate accuracy on unseen future events
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X[:split_idx], X[split_idx:]
    Y_train, Y_test = Y[:split_idx], Y[split_idx:]

    print(f"\n[Phase 1] Evaluating on held-out 20% test set ({len(X_test):,} rows)...")
    for j, name in enumerate(TARGETS):
        gbdt, mlp = _make_pair()
        gbdt.fit(X_train, Y_train[:, j])
        mlp.fit(X_train, Y_train[:, j])

        pred_blend = 0.5 * gbdt.predict(X_test) + 0.5 * mlp.predict(X_test)
        mae = mean_absolute_error(np.expm1(Y_test[:, j]), np.maximum(0.0, np.expm1(pred_blend)))
        print(f"  Target {name:<10} | Test MAE: {mae:.3f} events")

    # Phase 2: Refit final production ensemble on 100% of the catalog
    print(f"\n[Phase 2] Retraining final ensemble on 100% of data ({len(X):,} rows)...")
    final_gbdt, final_mlp = [], []
    for j, name in enumerate(TARGETS):
        gbdt, mlp = _make_pair()
        gbdt.fit(X, Y[:, j])
        mlp.fit(X, Y[:, j])
        final_gbdt.append(gbdt)
        final_mlp.append(mlp)

    os.makedirs("models", exist_ok=True)
    with open(MODEL_OUT, "wb") as f:
        pickle.dump(
            {
                "gbdt": final_gbdt,
                "mlp": final_mlp,
                "targets": TARGETS,
                "n_features": X.shape[1],
                "total_rows_trained": len(X),
            },
            f,
        )
    print(f"Saved 100%-trained AI Aftershock Ensemble (M4.5+ to M7+) to {MODEL_OUT}")

if __name__ == "__main__":
    train()