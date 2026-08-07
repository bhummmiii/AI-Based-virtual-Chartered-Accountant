"""Tax Record schema — matches TaxRecord model (UUID PKs, Numeric fields)."""

import uuid
from pydantic import BaseModel
from datetime import datetime
from decimal import Decimal


class TaxRecordResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    financial_year: str
    tax_type: str
    taxable_income: Decimal
    tds: Decimal
    advance_tax: Decimal
    total_tax: Decimal
    status: str
    created_at: datetime

    class Config:
        from_attributes = True
