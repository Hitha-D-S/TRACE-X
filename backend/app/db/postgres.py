"""
TRACE-X PostgreSQL Database — SQLAlchemy async engine + models.
Stores: users, cases, alert state, comments, audit logs, upload jobs.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional, List

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey,
    Integer, String, Text, JSON, Enum as SAEnum,
)
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, relationship

from app.core.config import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_uuid() -> str:
    return str(uuid.uuid4())


# ── SQLAlchemy base ──────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── Models ───────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id = Column(String, primary_key=True, default=new_uuid)
    email = Column(String, unique=True, nullable=False, index=True)
    name = Column(String, nullable=False)
    role = Column(String, nullable=False, default="investigator")
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    audit_logs = relationship("AuditLog", back_populates="user")


class AlertState(Base):
    """Mutable alert lifecycle state (stored in Postgres)."""
    __tablename__ = "alert_states"
    id = Column(String, primary_key=True)           # same ID as Neo4j Alert node
    status = Column(String, default="NEW")          # NEW / INVESTIGATING / ESCALATED / RESOLVED
    severity = Column(String, default="MEDIUM")     # LOW / MEDIUM / HIGH / CRITICAL
    assigned_to = Column(String, ForeignKey("users.id"), nullable=True)
    final_risk_score = Column(Float, default=0.0)
    alert_type = Column(String, nullable=False)
    entity_ids = Column(JSON, default=list)
    transaction_ids = Column(JSON, default=list)
    contributing_signals = Column(JSON, default=dict)
    evidence = Column(JSON, default=dict)
    resolution = Column(Text, nullable=True)
    investigator_notes = Column(Text, nullable=True)
    dataset_id = Column(String, nullable=True, index=True)
    source = Column(String, default="SYNTHETIC")    # SYNTHETIC / USER_UPLOAD
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    comments = relationship("AlertComment", back_populates="alert")
    audit_logs = relationship("AuditLog", back_populates="alert")


class AlertComment(Base):
    __tablename__ = "alert_comments"
    id = Column(String, primary_key=True, default=new_uuid)
    alert_id = Column(String, ForeignKey("alert_states.id"), nullable=False)
    user_id = Column(String, ForeignKey("users.id"), nullable=False)
    content = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    alert = relationship("AlertState", back_populates="comments")


class UploadJob(Base):
    """Tracks async file upload / ingestion jobs."""
    __tablename__ = "upload_jobs"
    id = Column(String, primary_key=True, default=new_uuid)
    filename = Column(String, nullable=False)
    file_hash = Column(String, nullable=False, index=True)  # idempotency
    status = Column(String, default="PENDING")              # PENDING / PROCESSING / DONE / FAILED
    rows_received = Column(Integer, default=0)
    rows_ingested = Column(Integer, default=0)
    rows_quarantined = Column(Integer, default=0)
    entities_created = Column(Integer, default=0)
    entities_matched = Column(Integer, default=0)
    dataset_id = Column(String, nullable=True, index=True)
    column_mapping = Column(JSON, default=dict)
    error_report = Column(JSON, default=list)
    created_by = Column(String, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AuditLog(Base):
    """Immutable audit trail for compliance."""
    __tablename__ = "audit_logs"
    id = Column(String, primary_key=True, default=new_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    alert_id = Column(String, ForeignKey("alert_states.id"), nullable=True)
    action = Column(String, nullable=False)   # VIEW / STATUS_CHANGE / NOTE / ASSIGN / EXPORT / AI_SUMMARY
    detail = Column(JSON, default=dict)
    ip_address = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow)

    user = relationship("User", back_populates="audit_logs")
    alert = relationship("AlertState", back_populates="audit_logs")


class EvaluationResult(Base):
    """Stores detection benchmark results for the Evaluation dashboard."""
    __tablename__ = "evaluation_results"
    id = Column(String, primary_key=True, default=new_uuid)
    run_at = Column(DateTime(timezone=True), default=utcnow)
    precision = Column(Float, default=0.0)
    recall = Column(Float, default=0.0)
    f1 = Column(Float, default=0.0)
    false_positive_rate = Column(Float, default=0.0)
    true_positives = Column(Integer, default=0)
    false_positives = Column(Integer, default=0)
    false_negatives = Column(Integer, default=0)
    true_negatives = Column(Integer, default=0)
    per_scenario = Column(JSON, default=dict)
    detection_latency_p50_ms = Column(Float, nullable=True)
    detection_latency_p95_ms = Column(Float, nullable=True)
    dataset_id = Column(String, nullable=True)


# ── Engine + Session ─────────────────────────────────────────

_engine = None
_session_factory = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.postgres_url,
            echo=False,
            pool_size=10,
            max_overflow=20,
        )
    return _engine


def get_session_factory():
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            get_engine(), expire_on_commit=False, class_=AsyncSession
        )
    return _session_factory


async def create_tables() -> None:
    """Create all tables (run on startup)."""
    async with get_engine().begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields an async DB session."""
    async with get_session_factory()() as session:
        yield session
