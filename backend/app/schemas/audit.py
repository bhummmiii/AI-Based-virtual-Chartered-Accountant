"""Audit Report schema — matches AuditReport model (UUID PKs)."""
import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from decimal import Decimal


class AuditReportResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    audit_type: str
    audit_status: str
    risk_score: Optional[Decimal] = None
    findings: Optional[str] = None
    recommendations: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
