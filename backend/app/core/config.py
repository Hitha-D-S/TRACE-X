"""
TRACE-X Core Configuration
All settings loaded from environment variables with safe defaults.
"""
from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import List

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Application ─────────────────────────────────────────
    environment: str = "development"
    log_level: str = "INFO"
    app_name: str = "TRACE-X"
    app_version: str = "1.0.0"
    debug: bool = False

    # ── PostgreSQL ──────────────────────────────────────────
    postgres_url: str = (
        "postgresql+asyncpg://tracex:tracexpass@localhost:5432/tracex"
    )

    # ── Neo4j ───────────────────────────────────────────────
    neo4j_uri: str = "bolt://localhost:7687"
    neo4j_user: str = "neo4j"
    neo4j_password: str = "tracexneo4j"

    # ── Redis ───────────────────────────────────────────────
    redis_url: str = "redis://localhost:6379/0"

    # ── Kafka / Redpanda ────────────────────────────────────
    kafka_bootstrap_servers: str = "localhost:19092"
    kafka_transaction_topic: str = "tracex.transactions"
    kafka_dlq_topic: str = "tracex.dlq"
    direct_ingest_mode: bool = True  # bypass Kafka for dev/demo

    # ── AI Provider ─────────────────────────────────────────
    gemini_api_key: str = ""
    gemini_model: str = "gemini-1.5-flash"

    # ── Security ────────────────────────────────────────────
    jwt_secret_key: str = "tracex-demo-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 480

    # ── CORS ────────────────────────────────────────────────
    cors_origins: str = "http://localhost:3000"

    @property
    def cors_origins_list(self) -> List[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    # ── Detection Thresholds (DEMO values — not legal) ──────
    structuring_threshold: int = 10_000        # INR — demo value only
    rapid_passthrough_seconds: int = 600
    burst_window_seconds: int = 3_600
    burst_count_threshold: int = 10
    dormancy_threshold_days: int = 90
    circular_flow_max_depth: int = 4
    revenue_mismatch_ratio: float = 5.0
    round_amount_threshold: int = 10_000
    max_graph_traversal_depth: int = 4

    # ── Risk Fusion Weights ──────────────────────────────────
    risk_weight_rule: float = 0.30
    risk_weight_anomaly: float = 0.25
    risk_weight_graph: float = 0.25
    risk_weight_temporal: float = 0.20

    # ── Risk Level Thresholds ────────────────────────────────
    risk_low_max: int = 29
    risk_medium_max: int = 59
    risk_high_max: int = 79

    # ── Upload Limits ────────────────────────────────────────
    max_upload_size_mb: int = 50
    max_upload_rows: int = 100_000

    # ── Synthetic Data ───────────────────────────────────────
    synthetic_seed: int = 42
    synthetic_normal_count: int = 500
    synthetic_suspicious_count: int = 50

    # ── Artifacts ────────────────────────────────────────────
    artifacts_dir: str = "artifacts"

    @property
    def has_gemini_key(self) -> bool:
        return bool(self.gemini_api_key and self.gemini_api_key.strip())

    def get_risk_level(self, score: float) -> str:
        """Map a 0–100 score to a risk level label."""
        if score <= self.risk_low_max:
            return "LOW"
        if score <= self.risk_medium_max:
            return "MEDIUM"
        if score <= self.risk_high_max:
            return "HIGH"
        return "CRITICAL"


@lru_cache
def get_settings() -> Settings:
    return Settings()
