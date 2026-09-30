"""GST Record schemas — matches GSTRecord model (UUID PKs, Numeric tax fields)."""

import uuid
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class GSTRecordCreate(BaseModel):
    client_id: uuid.UUID
    gst_period: str
    gst_type: str = "GSTR-3B"
    taxable_amount: Decimal = Decimal("0.00")
    cgst: Decimal = Decimal("0.00")
    sgst: Decimal = Decimal("0.00")
    igst: Decimal = Decimal("0.00")
    total_tax: Optional[Decimal] = None
    filing_status: str = "pending"
    due_date: Optional[date] = None


class GSTRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    gst_period: str
    gst_type: str
    taxable_amount: Decimal
    cgst: Decimal
    sgst: Decimal
    igst: Decimal
    total_tax: Decimal
    filing_status: str
    due_date: Optional[date] = None
    created_at: datetime
