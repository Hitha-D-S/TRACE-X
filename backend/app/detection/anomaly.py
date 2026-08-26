"""
TRACE-X Isolation Forest Anomaly Detection
Behavioral ML for unsupervised anomaly scoring.
Features are computed from transaction statistics only — no target leakage.
"""
from __future__ import annotations

import json
import os
import pickle
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.core.config import get_settings
from app.core.logging_config import get_logger

logger = get_logger(__name__)
settings = get_settings()

# ── Feature Schema (order matters for model input) ──────────────
FEATURE_NAMES = [
    "amount",
    "amount_log",
    "hour_of_day",
    "day_of_week",
    "is_round_amount",
    "src_out_degree",
    "dst_in_degree",
    "src_tx_count_24h",
    "dst_tx_count_24h",
    "amount_vs_src_mean",
]

MODEL_VERSION = "iso-forest-v1.0"
ARTIFACT_PATH = os.path.join(settings.artifacts_dir, "isolation_forest.pkl")
SCALER_PATH = os.path.join(settings.artifacts_dir, "scaler.pkl")
META_PATH = os.path.join(settings.artifacts_dir, "model_meta.json")


# ── Feature Extraction ───────────────────────────────────────

def extract_features(
    tx: Dict[str, Any],
    historical_txs: List[Dict[str, Any]],
) -> np.ndarray:
    """
    Extract a 10-feature vector for a single transaction.
    Uses only historical data to avoid target leakage.
    """
    from dateutil.parser import parse as parse_dt

    amount = float(tx.get("amount", 0))
    ts_raw = tx.get("timestamp", datetime.now(timezone.utc))
    if isinstance(ts_raw, str):
        ts = parse_dt(ts_raw)
    elif isinstance(ts_raw, datetime):
        ts = ts_raw
    else:
        ts = datetime.now(timezone.utc)

    src = tx.get("source_account_id", "")
    dst = tx.get("destination_account_id", "")

    # Compute historical statistics from prior transactions only
    src_txs = [t for t in historical_txs if t.get("source_account_id") == src]
    dst_txs = [t for t in historical_txs if t.get("destination_account_id") == dst]

    # Count transactions in last 24h for src and dst
    from datetime import timedelta
    cutoff_24h = ts - timedelta(hours=24)

    def _ts(t: Dict) -> datetime:
        raw = t.get("timestamp", datetime.now(timezone.utc))
        if isinstance(raw, str):
            from dateutil.parser import parse
            return parse(raw)
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)

    src_count_24h = sum(1 for t in src_txs if _ts(t) >= cutoff_24h)
    dst_count_24h = sum(1 for t in dst_txs if _ts(t) >= cutoff_24h)

    src_amounts = [float(t.get("amount", 0)) for t in src_txs]
    src_mean = np.mean(src_amounts) if src_amounts else amount
    amount_vs_src_mean = amount / max(src_mean, 1.0)

    features = [
        amount,                                          # raw amount
        np.log1p(amount),                               # log-normalized amount
        float(ts.hour),                                 # hour of day
        float(ts.weekday()),                            # day of week
        float(amount % 1000 == 0 and amount >= 10000), # is large round amount
        float(len(src_txs)),                            # source out-degree (approx)
        float(len(dst_txs)),                            # destination in-degree (approx)
        float(src_count_24h),                           # src 24h count
        float(dst_count_24h),                           # dst 24h count
        float(amount_vs_src_mean),                      # amount relative to src baseline
    ]
    return np.array(features, dtype=np.float32)


def extract_batch_features(
    transactions: List[Dict[str, Any]],
) -> Tuple[np.ndarray, List[str]]:
    """
    Extract feature matrix for a list of transactions.
    Uses rolling historical context (each tx only sees prior txs).
    Returns (feature_matrix, tx_ids).
    """
    features_list = []
    tx_ids = []

    for i, tx in enumerate(transactions):
        # Only use transactions before this one (no leakage)
        historical = transactions[:i]
        feats = extract_features(tx, historical)
        features_list.append(feats)
        tx_ids.append(tx.get("id", str(i)))

    if not features_list:
        return np.empty((0, len(FEATURE_NAMES))), []

    X = np.stack(features_list)
    # Handle NaN/inf
    X = np.nan_to_num(X, nan=0.0, posinf=10.0, neginf=0.0)
    return X, tx_ids


# ── Model Training ───────────────────────────────────────────

def train_model(
    transactions: List[Dict[str, Any]],
    contamination: float = 0.08,
    n_estimators: int = 100,
    random_state: int = 42,
) -> Dict[str, Any]:
    """Train Isolation Forest on a transaction dataset. Saves versioned artifacts."""
    logger.info("Training Isolation Forest", n_samples=len(transactions))
    X, _ = extract_batch_features(transactions)

    if X.shape[0] < 10:
        logger.warning("Too few samples to train model", n=X.shape[0])
        return {"status": "skipped", "reason": "insufficient_samples"}

    # Scale features
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # Train model
    model = IsolationForest(
        n_estimators=n_estimators,
        contamination=contamination,
        random_state=random_state,
        max_features=1.0,
    )
    model.fit(X_scaled)

    # Save artifacts
    os.makedirs(settings.artifacts_dir, exist_ok=True)
    with open(ARTIFACT_PATH, "wb") as f:
        pickle.dump(model, f)
    with open(SCALER_PATH, "wb") as f:
        pickle.dump(scaler, f)

    meta = {
        "model_version": MODEL_VERSION,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_samples": X.shape[0],
        "n_features": X.shape[1],
        "feature_names": FEATURE_NAMES,
        "contamination": contamination,
        "n_estimators": n_estimators,
    }
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Model trained and saved", path=ARTIFACT_PATH)
    return {"status": "trained", **meta}


# ── Model Loading ────────────────────────────────────────────

_model: Optional[IsolationForest] = None
_scaler: Optional[StandardScaler] = None
_model_meta: Optional[Dict] = None


def load_model() -> bool:
    """Load saved model and scaler. Returns True if successful."""
    global _model, _scaler, _model_meta
    try:
        if not os.path.exists(ARTIFACT_PATH):
            return False
        with open(ARTIFACT_PATH, "rb") as f:
            _model = pickle.load(f)
        with open(SCALER_PATH, "rb") as f:
            _scaler = pickle.load(f)
        if os.path.exists(META_PATH):
            with open(META_PATH) as f:
                _model_meta = json.load(f)
        logger.info("Anomaly model loaded", version=_model_meta.get("model_version") if _model_meta else "unknown")
        return True
    except Exception as e:
        logger.warning("Failed to load anomaly model", error=str(e))
        _model = None
        _scaler = None
        return False


def is_model_loaded() -> bool:
    return _model is not None and _scaler is not None


# ── Scoring ──────────────────────────────────────────────────

def score_transaction(
    tx: Dict[str, Any],
    historical_txs: List[Dict[str, Any]],
) -> Tuple[float, List[Tuple[str, float]]]:
    """
    Score a single transaction.
    Returns (anomaly_score_0_to_1, feature_contributions).
    Falls back to 0.0 if no model is loaded.
    """
    if not is_model_loaded():
        return 0.0, []

    feats = extract_features(tx, historical_txs).reshape(1, -1)
    feats = np.nan_to_num(feats, nan=0.0, posinf=10.0, neginf=0.0)
    feats_scaled = _scaler.transform(feats)

    # Raw score: -1 (anomaly) to 1 (normal)
    raw = _model.score_samples(feats_scaled)[0]
    # Normalize to 0-1 where 1 = most anomalous
    anomaly_score = float(np.clip((0.5 - raw * 0.5), 0.0, 1.0))

    # Feature contributions (simple: |scaled_value| as proxy)
    contributions = [
        (FEATURE_NAMES[i], float(abs(feats_scaled[0][i])))
        for i in range(len(FEATURE_NAMES))
    ]
    contributions.sort(key=lambda x: x[1], reverse=True)

    return anomaly_score, contributions[:5]


def score_batch(
    transactions: List[Dict[str, Any]],
) -> Dict[str, float]:
    """Score a batch of transactions. Returns {tx_id: anomaly_score}."""
    if not is_model_loaded():
        return {tx.get("id", str(i)): 0.0 for i, tx in enumerate(transactions)}

    X, tx_ids = extract_batch_features(transactions)
    if X.shape[0] == 0:
        return {}

    X_scaled = _scaler.transform(X)
    raw_scores = _model.score_samples(X_scaled)
    anomaly_scores = np.clip(0.5 - raw_scores * 0.5, 0.0, 1.0)

    return {tx_ids[i]: float(anomaly_scores[i]) for i in range(len(tx_ids))}


def get_model_metadata() -> Optional[Dict]:
    return _model_meta
