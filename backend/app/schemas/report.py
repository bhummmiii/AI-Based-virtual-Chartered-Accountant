"""
Report Pydantic Schemas.
"""

from pydantic import BaseModel
from datetime import datetime


class ReportResponse(BaseModel):
    id: int
    client_id: int
    report_type: str
    report_url: str
    generated_at: datetime

    class Config:
        from_attributes = True
