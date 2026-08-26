"""
TRACE-X Transaction Domain Models (Pydantic)
All monetary amounts are stored as integer minor units (paise) internally.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class TransactionType(str, Enum):
    NEFT = "NEFT"
    RTGS = "RTGS"
    IMPS = "IMPS"
    UPI = "UPI"
    CASH = "CASH"
    CHEQUE = "CHEQUE"
    WIRE = "WIRE"
    INTERNAL = "INTERNAL"
    OTHER = "OTHER"


class TransactionChannel(str, Enum):
    MOBILE = "MOBILE"
    INTERNET = "INTERNET"
    BRANCH = "BRANCH"
    ATM = "ATM"
    POS = "POS"
    API = "API"
    OTHER = "OTHER"


class TransactionStatus(str, Enum):
    PENDING = "PENDING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REVERSED = "REVERSED"


class TransactionCreate(BaseModel):
    """Input schema for a single transaction event."""
    id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    source_account_id: str = Field(..., min_length=1, max_length=100)
    destination_account_id: str = Field(..., min_length=1, max_length=100)
    amount: Decimal = Field(..., gt=0, description="Amount in major currency units (e.g. INR)")
    currency: str = Field(default="INR", max_length=3)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    transaction_type: TransactionType = TransactionType.OTHER
    channel: TransactionChannel = TransactionChannel.OTHER
    location: Optional[str] = Field(default=None, max_length=200)
    reference: Optional[str] = Field(default=None, max_length=500)
    status: TransactionStatus = TransactionStatus.COMPLETED



    # Dataset tracking
    dataset_id: Optional[str] = Field(default="SYNTHETIC")
    source: str = Field(default="SYNTHETIC")  # SYNTHETIC | USER_UPLOAD

    # Metadata fields for owner & bank names visualization
    sender_name: Optional[str] = None
    receiver_name: Optional[str] = None
    source_bank_name: Optional[str] = None
    destination_bank_name: Optional[str] = None
    sender_type: Optional[str] = None
    receiver_type: Optional[str] = None

    # Ground-truth labels (only set by synthetic generator or evaluation runs)
    is_suspicious: Optional[bool] = None
    scenario_label: Optional[str] = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def ensure_utc(cls, v: Any) -> datetime:
        if isinstance(v, str):
            from dateutil.parser import parse
            v = parse(v)
        if isinstance(v, datetime) and v.tzinfo is None:
            v = v.replace(tzinfo=timezone.utc)
        return v

    @field_validator("currency")
    @classmethod
    def uppercase_currency(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def accounts_must_differ(self) -> "TransactionCreate":
        if self.source_account_id == self.destination_account_id:
            raise ValueError("source and destination accounts must differ")
        return self


class TransactionRiskScores(BaseModel):
    """Risk component scores attached after detection pipeline runs."""
    anomaly_score: float = Field(default=0.0, ge=0.0, le=1.0)
    rule_score: float = Field(default=0.0, ge=0.0, le=1.0)
    temporal_score: float = Field(default=0.0, ge=0.0, le=1.0)
    graph_score: float = Field(default=0.0, ge=0.0, le=1.0)
    final_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_level: str = "LOW"


class TransactionFull(TransactionCreate, TransactionRiskScores):
    """Complete transaction object after pipeline processing."""

    def to_neo4j_params(self) -> Dict[str, Any]:
        """Serialize for Neo4j parameterized query."""
        return {
            "id": self.id,
            "source_account_id": self.source_account_id,
            "destination_account_id": self.destination_account_id,
            "amount": float(self.amount),
            "currency": self.currency,
            "timestamp": self.timestamp.isoformat(),
            "transaction_type": self.transaction_type.value,
            "channel": self.channel.value,
            "location": self.location or "",
            "reference": self.reference or "",
            "status": self.status.value,
            "anomaly_score": self.anomaly_score,
            "rule_score": self.rule_score,
            "temporal_score": self.temporal_score,
            "graph_score": self.graph_score,
            "final_risk_score": self.final_risk_score,
            "dataset_id": self.dataset_id or "SYNTHETIC",
            "source": self.source,
        }


class BatchTransactionCreate(BaseModel):
    transactions: List[TransactionCreate] = Field(..., min_length=1, max_length=1000)
    dataset_id: Optional[str] = None
