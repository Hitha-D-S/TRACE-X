"""
TRACE-X Alert Domain Models (Pydantic)
Alert = a risk-flagging event containing structured evidence.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class AlertSeverity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class AlertStatus(str, Enum):
    NEW = "NEW"
    INVESTIGATING = "INVESTIGATING"
    ESCALATED = "ESCALATED"
    RESOLVED = "RESOLVED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class RuleEvidence(BaseModel):
    """Structured evidence from a single rule detector."""
    rule_id: str
    rule_version: str = "1.0"
    entity_ids: List[str] = Field(default_factory=list)
    transaction_ids: List[str] = Field(default_factory=list)
    observed_value: Dict[str, Any] = Field(default_factory=dict)
    threshold: Dict[str, Any] = Field(default_factory=dict)
    time_window: Dict[str, Any] = Field(default_factory=dict)
    explanation: str
    score: float = Field(ge=0.0, le=1.0)


class RiskComponents(BaseModel):
    rule_score: float = Field(default=0.0, ge=0.0, le=1.0)
    anomaly_score: float = Field(default=0.0, ge=0.0, le=1.0)
    graph_score: float = Field(default=0.0, ge=0.0, le=1.0)
    temporal_score: float = Field(default=0.0, ge=0.0, le=1.0)
    final_risk_score: float = Field(default=0.0, ge=0.0, le=100.0)
    risk_level: str = "LOW"
    top_features: List[str] = Field(default_factory=list)
    model_version: Optional[str] = None
    rule_versions: Dict[str, str] = Field(default_factory=dict)
    human_explanation: str = ""


class Alert(BaseModel):
    """Complete alert object (immutable after creation; status in Postgres)."""
    id: str = Field(default_factory=lambda: f"ALT-{uuid.uuid4().hex[:8].upper()}")
    alert_type: str
    severity: AlertSeverity = AlertSeverity.MEDIUM
    status: AlertStatus = AlertStatus.NEW

    entity_ids: List[str] = Field(default_factory=list)
    transaction_ids: List[str] = Field(default_factory=list)
    cluster_id: Optional[str] = None

    risk_components: RiskComponents = Field(default_factory=RiskComponents)
    triggered_rules: List[RuleEvidence] = Field(default_factory=list)
    contributing_signals: Dict[str, float] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)

    assigned_to: Optional[str] = None
    resolution: Optional[str] = None
    investigator_notes: Optional[str] = None

    dataset_id: Optional[str] = "SYNTHETIC"
    source: str = "SYNTHETIC"

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Ground-truth (set by evaluation runs only)
    is_true_positive: Optional[bool] = None
    scenario_label: Optional[str] = None

    def to_brief_dict(self) -> Dict[str, Any]:
        """Compact representation for SSE/WS streaming."""
        return {
            "id": self.id,
            "alert_type": self.alert_type,
            "severity": self.severity.value,
            "final_risk_score": self.risk_components.final_risk_score,
            "risk_level": self.risk_components.risk_level,
            "entity_count": len(self.entity_ids),
            "transaction_count": len(self.transaction_ids),
            "created_at": self.created_at.isoformat(),
            "dataset_id": self.dataset_id,
        }


class AlertUpdate(BaseModel):
    status: Optional[AlertStatus] = None
    assigned_to: Optional[str] = None
    resolution: Optional[str] = None
    investigator_notes: Optional[str] = None


class AlertNoteCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)


class AlertFilters(BaseModel):
    severity: Optional[AlertSeverity] = None
    status: Optional[AlertStatus] = None
    alert_type: Optional[str] = None
    dataset_id: Optional[str] = None
    min_risk: Optional[float] = None
    max_risk: Optional[float] = None
    from_date: Optional[datetime] = None
    to_date: Optional[datetime] = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)
