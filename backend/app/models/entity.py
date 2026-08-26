"""
TRACE-X Entity Domain Models (Pydantic)
Covers Person, Company, BankAccount and all shared-attribute nodes.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class EntityType(str, Enum):
    PERSON = "PERSON"
    COMPANY = "COMPANY"
    BANK_ACCOUNT = "BANK_ACCOUNT"
    ADDRESS = "ADDRESS"
    PHONE = "PHONE"
    EMAIL = "EMAIL"
    PAN = "PAN"
    GSTIN = "GSTIN"


class CompanyStatus(str, Enum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    DISSOLVED = "DISSOLVED"
    STRUCK_OFF = "STRUCK_OFF"


class AccountType(str, Enum):
    SAVINGS = "SAVINGS"
    CURRENT = "CURRENT"
    OVERDRAFT = "OVERDRAFT"
    FIXED_DEPOSIT = "FIXED_DEPOSIT"
    NRI = "NRI"


# ── Core Entity Models ───────────────────────────────────────

class Person(BaseModel):
    id: str = Field(default_factory=lambda: f"PER-{uuid.uuid4().hex[:8].upper()}")
    name: str
    date_of_birth: Optional[date] = None
    risk_score: float = 0.0
    dataset_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Company(BaseModel):
    id: str = Field(default_factory=lambda: f"COM-{uuid.uuid4().hex[:8].upper()}")
    legal_name: str
    incorporation_date: Optional[date] = None
    industry: Optional[str] = None
    status: CompanyStatus = CompanyStatus.ACTIVE
    registered_capital: Optional[float] = None
    annual_revenue: Optional[float] = None
    employee_count: Optional[int] = None
    risk_score: float = 0.0
    dataset_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class BankAccount(BaseModel):
    id: str = Field(default_factory=lambda: f"ACC-{uuid.uuid4().hex[:8].upper()}")
    masked_number: str = "****0000"
    bank_name: str = "Unknown"
    branch: Optional[str] = None
    account_type: AccountType = AccountType.CURRENT
    opening_date: Optional[date] = None
    status: str = "ACTIVE"
    balance: float = 0.0
    risk_score: float = 0.0
    owner_id: Optional[str] = None        # Person.id or Company.id
    owner_type: Optional[str] = None      # PERSON | COMPANY
    dataset_id: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ── Shared-Attribute Nodes ───────────────────────────────────

class AddressNode(BaseModel):
    id: str = Field(default_factory=lambda: f"ADDR-{uuid.uuid4().hex[:8].upper()}")
    full_address: str
    city: Optional[str] = None
    state: Optional[str] = None
    pin: Optional[str] = None
    dataset_id: Optional[str] = None


class PhoneNode(BaseModel):
    id: str = Field(default_factory=lambda: f"PHN-{uuid.uuid4().hex[:8].upper()}")
    masked_number: str   # e.g., "+91-98****1234"
    dataset_id: Optional[str] = None


class EmailNode(BaseModel):
    id: str = Field(default_factory=lambda: f"EML-{uuid.uuid4().hex[:8].upper()}")
    masked_address: str   # e.g., "j***@example.com"
    domain: str
    dataset_id: Optional[str] = None


class PANNode(BaseModel):
    id: str = Field(default_factory=lambda: f"PAN-{uuid.uuid4().hex[:8].upper()}")
    masked_pan: str       # e.g., "ABCDE****F"  — never full PAN
    dataset_id: Optional[str] = None


class GSTINNode(BaseModel):
    id: str = Field(default_factory=lambda: f"GST-{uuid.uuid4().hex[:8].upper()}")
    masked_gstin: str     # e.g., "27ABCDE****F1Z5"
    dataset_id: Optional[str] = None


# ── Entity Resolution Models ─────────────────────────────────

class MatchAttribute(BaseModel):
    attribute: str
    weight: float
    value_a: Optional[str] = None
    value_b: Optional[str] = None
    match_type: str = "EXACT"  # EXACT | FUZZY | BEHAVIORAL


class EntityMatch(BaseModel):
    entity_a_id: str
    entity_b_id: str
    match_score: float
    confidence: str     # HIGH | MEDIUM | LOW | WEAK
    matched_attributes: List[MatchAttribute]
    explanation: str
    requires_review: bool = True


class EntityResolutionRequest(BaseModel):
    entity_ids: List[str] = Field(..., min_length=2)
    dataset_id: Optional[str] = None


class EntityRiskResponse(BaseModel):
    entity_id: str
    entity_type: str
    risk_score: float
    risk_level: str
    contributing_factors: List[str]
    triggered_alerts: List[str]
    related_entities: List[str]
    explanation: str
