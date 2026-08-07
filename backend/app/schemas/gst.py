"""GST Record schema — matches GSTRecord model (UUID PKs, Numeric tax fields)."""

import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class GSTRecordResponse(BaseModel):
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

    class Config:
        from_attributes = True
