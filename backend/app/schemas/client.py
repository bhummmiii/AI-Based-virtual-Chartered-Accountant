"""
Client Pydantic Schemas — fully aligned to UUID models.

Frontend field  ←→  DB field
company         ←→  company_name
name            ←→  contact_person
type            ←→  client_type
gstin           ←→  gst_number
risk            ←→  risk_level
id (display)    ←→  client_code  e.g. "CLI-001"
db_id           ←→  Client.id    (UUID, sent as string to frontend)
"""

import re
import uuid
from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime

from app.schemas.accounting import AccountingRecordResponse
from app.schemas.gst import GSTRecordResponse
from app.schemas.tax import TaxRecordResponse
from app.schemas.audit import AuditReportResponse
from app.schemas.invoice import InvoiceResponse
from app.schemas.document import DocumentResponse

GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")
PAN_RE   = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]{1}$")


# ── Create ────────────────────────────────────────────────────
class ClientCreate(BaseModel):
    """
    Payload for creating a new client.
    audit and tax are NOT accepted from frontend — backend assigns
    "pending" automatically. Future Auditing/GST modules will update them.
    """
    company:        str   = Field(..., min_length=1, max_length=255)
    name:           str   = Field(..., min_length=1, max_length=255)
    type:           str   = Field(default="Company")
    gstin:          Optional[str] = None
    revenue:        float = Field(default=0.0, ge=0)
    status:         str   = Field(default="Active")
    gst:            str   = Field(default="Filed")
    # audit and tax intentionally removed — hardcoded to "Pending" in service
    risk:           str   = Field(default="Low")
    pan:            Optional[str] = None
    email:          Optional[str] = None
    phone:          Optional[str] = None
    address:        Optional[str] = None
    city:           Optional[str] = None
    state:          Optional[str] = None
    country:        Optional[str] = Field(default="India")
    industry:       Optional[str] = None
    # ── Extended fields ──────────────────────────────────────
    clientType:     Optional[str] = Field(default="Monthly", description="Monthly | Quarterly")
    contactNumber:  Optional[str] = Field(default=None, description="Mobile number (10–15 digits)")
    emailAddress:   Optional[str] = Field(default=None, description="Client email address")
    location:       Optional[str] = Field(default=None, description="City, State")

    @field_validator("gstin")
    @classmethod
    def v_gstin(cls, v):
        if not v or not v.strip(): return None
        v = v.strip().upper()
        if not GSTIN_RE.match(v): raise ValueError("Invalid GSTIN. Expected: 27AABCN1234R1Z5")
        return v

    @field_validator("pan")
    @classmethod
    def v_pan(cls, v):
        if not v or not v.strip(): return None
        v = v.strip().upper()
        if not PAN_RE.match(v): raise ValueError("Invalid PAN. Expected: AABCN1234R")
        return v

    @field_validator("phone")
    @classmethod
    def v_phone(cls, v):
        if not v or not v.strip(): return None
        digits = re.sub(r"[\s\-\+\(\)]", "", v)
        if not digits.isdigit() or not (7 <= len(digits) <= 15):
            raise ValueError("Phone must be 7–15 digits")
        return v.strip()


# ── Update ────────────────────────────────────────────────────
class ClientUpdate(BaseModel):
    company:        Optional[str]   = Field(default=None, min_length=1, max_length=255)
    name:           Optional[str]   = Field(default=None, min_length=1, max_length=255)
    type:           Optional[str]   = None
    gstin:          Optional[str]   = None
    revenue:        Optional[float] = Field(default=None, ge=0)
    status:         Optional[str]   = None
    gst:            Optional[str]   = None
    audit:          Optional[str]   = None
    tax:            Optional[str]   = None
    risk:           Optional[str]   = None
    pan:            Optional[str]   = None
    email:          Optional[str]   = None
    phone:          Optional[str]   = None
    address:        Optional[str]   = None
    city:           Optional[str]   = None
    state:          Optional[str]   = None
    country:        Optional[str]   = None
    industry:       Optional[str]   = None
    # ── New fields ──────────────────────────────────────────
    clientType:     Optional[str]   = None
    contactNumber:  Optional[str]   = None
    emailAddress:   Optional[str]   = None
    location:       Optional[str]   = None

    @field_validator("gstin")
    @classmethod
    def v_gstin(cls, v):
        if not v or not v.strip(): return None
        v = v.strip().upper()
        if not GSTIN_RE.match(v): raise ValueError("Invalid GSTIN")
        return v

    @field_validator("pan")
    @classmethod
    def v_pan(cls, v):
        if not v or not v.strip(): return None
        v = v.strip().upper()
        if not PAN_RE.match(v): raise ValueError("Invalid PAN")
        return v


# ── Card (Workspace list item) ────────────────────────────────
class ClientCardResponse(BaseModel):
    """Matches the React Client TypeScript type exactly."""
    id:           str            # client_code  e.g. "CLI-001"
    name:         str            # contact_person
    company:      str            # company_name
    type:         str            # title-cased client_type
    gstin:        Optional[str] = None
    revenue:      float         = 0.0
    status:       str           = "Active"
    gst:          str           = "Pending"
    audit:        str           = "Pending"
    tax:          str           = "Pending"
    risk:         str           = "Low"
    lastActivity: str           = "Recently"
    avatar:       str           = "??"
    db_id:        str           # UUID string — used for PUT/DELETE/dashboard API calls

    class Config:
        from_attributes = True


# ── Full profile ──────────────────────────────────────────────
class ClientResponse(BaseModel):
    id:             uuid.UUID
    client_code:    str
    company_name:   str
    contact_person: str
    client_type:    str
    email:          Optional[str] = None
    phone:          Optional[str] = None
    gst_number:     Optional[str] = None
    pan_number:     Optional[str] = None
    address:        Optional[str] = None
    city:           Optional[str] = None
    state:          Optional[str] = None
    country:        Optional[str] = None
    industry:       Optional[str] = None
    risk_level:     str
    status:         str
    # ── New fields ──────────────────────────────────────────
    billing_cycle:  Optional[str] = None
    contact_number: Optional[str] = None
    email_address:  Optional[str] = None
    location:       Optional[str] = None
    created_at:     datetime
    updated_at:     datetime

    class Config:
        from_attributes = True


# ── Dashboard (single request) ────────────────────────────────
class ClientDashboardResponse(BaseModel):
    client:   ClientResponse
    gst:      List[GSTRecordResponse]      = []
    tax:      List[TaxRecordResponse]      = []
    audit:    List[AuditReportResponse]    = []
    invoices: List[InvoiceResponse]        = []
    documents: List[DocumentResponse]      = []
    accounting: List[AccountingRecordResponse] = []


# ── Overview KPIs ─────────────────────────────────────────────
class ClientOverviewResponse(BaseModel):
    client_id:         str   # UUID as string
    company_name:      str
    risk_level:        str   = "Low"
    compliance_status: str   = "compliant"
    gst_status:        Optional[str] = None
    tax_status:        Optional[str] = None
    audit_status:      Optional[str] = None


# ── Activity history ──────────────────────────────────────────
class ActivityItem(BaseModel):
    id:          str   # UUID as string
    type:        str
    title:       str
    description: str
    date:        datetime
    status:      Optional[str] = None


class ClientHistoryResponse(BaseModel):
    client_id:  str
    activities: List[ActivityItem] = []
