"""Invoice schema — matches Invoice model (UUID PKs, vendor_name, Numeric amount)."""

import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    invoice_number: str
    vendor_name: str
    invoice_date: date
    amount: Decimal
    currency: str
    ocr_text: Optional[str] = None
    translated_text: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
