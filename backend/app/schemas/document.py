"""Document schema — matches Document model (UUID PKs, file_name/file_type/storage_path)."""

import uuid
from pydantic import BaseModel
from datetime import datetime


class DocumentResponse(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    file_name: str
    file_type: str
    storage_path: str
    uploaded_at: datetime

    class Config:
        from_attributes = True
