"""Accounting Record schema — matches AccountingRecord model (UUID, Numeric fields)."""
import uuid
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime
from decimal import Decimal


class AccountingRecordResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    transaction_date: date
    voucher_type: str
    description: Optional[str] = None
    debit: Decimal
    credit: Decimal
    category: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
