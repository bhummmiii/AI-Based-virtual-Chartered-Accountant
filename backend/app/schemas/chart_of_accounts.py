"""
Pydantic Schemas for Chart of Accounts.
Validates account codes, ICAI classifications, and hierarchy.
"""

import uuid
from typing import Optional, List, Literal
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


AccountTypeEnum = Literal["asset", "liability", "equity", "revenue", "expense"]


class AccountBase(BaseModel):
    account_code: str = Field(..., min_length=1, max_length=50, description="Unique account code, e.g. '1010', '2010'")
    account_name: str = Field(..., min_length=1, max_length=255, description="Full account ledger title")
    account_type: AccountTypeEnum = Field(..., description="ICAI classification: asset | liability | equity | revenue | expense")
    account_subgroup: Optional[str] = Field(None, max_length=100, description="Subgroup: sundry_debtors, sundry_creditors, bank_accounts, duties_and_taxes, etc.")
    role: Optional[str] = Field(None, max_length=50, description="Role: OUTPUT_CGST, OUTPUT_SGST, OUTPUT_IGST, INPUT_CGST, INPUT_SGST, INPUT_IGST, SALES, SALES_RETURN, PURCHASE, PURCHASE_RETURN, DEBTORS, CREDITORS, OTHER_INCOME")
    parent_account_id: Optional[uuid.UUID] = Field(None, description="Parent account ID for nested hierarchy")
    description: Optional[str] = Field(None, description="Optional ledger description or notes")
    is_active: bool = Field(True, description="Active status for transaction posting")

    @field_validator("account_code")
    @classmethod
    def clean_code(cls, v: str) -> str:
        code = v.strip()
        if not code:
            raise ValueError("Account code cannot be blank")
        return code

    @field_validator("account_name")
    @classmethod
    def clean_name(cls, v: str) -> str:
        name = v.strip()
        if not name:
            raise ValueError("Account name cannot be blank")
        return name


class AccountCreate(AccountBase):
    client_id: uuid.UUID = Field(..., description="Client ID who owns this account")


class AccountUpdate(BaseModel):
    account_name: Optional[str] = Field(None, min_length=1, max_length=255)
    account_subgroup: Optional[str] = Field(None, max_length=100)
    role: Optional[str] = Field(None, max_length=50)
    parent_account_id: Optional[uuid.UUID] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

    @field_validator("account_name")
    @classmethod
    def clean_name(cls, v: Optional[str]) -> Optional[str]:
        if v is not None:
            name = v.strip()
            if not name:
                raise ValueError("Account name cannot be blank")
            return name
        return v


class AccountResponse(AccountBase):
    id: uuid.UUID
    client_id: uuid.UUID
    is_system: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AccountTreeNodeResponse(AccountResponse):
    sub_accounts: List["AccountTreeNodeResponse"] = []

    class Config:
        from_attributes = True


class DefaultCoaInitResponse(BaseModel):
    client_id: uuid.UUID
    created_count: int
    skipped_count: int
    total_accounts: int
    message: str
