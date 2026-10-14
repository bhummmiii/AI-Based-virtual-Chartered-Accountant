"""
Pydantic schemas for Government Updates module.
"""

import uuid
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, ConfigDict


class GovSourceResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    base_url: str
    domain: str
    tier: int
    scope: str
    state_code: Optional[str] = None
    method: str
    enabled: bool
    status: str
    robots_ok: bool
    captcha_detected: bool
    tos_note: Optional[str] = None
    crawl_delay_seconds: float
    last_run_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    last_success_at: Optional[datetime] = None
    consecutive_failures: int = 0
    failure_stage: Optional[str] = None
    last_error: Optional[str] = None
    next_retry_at: Optional[datetime] = None
    last_probe_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class GovUpdateResponse(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    source_name: Optional[str] = None
    source_code: Optional[str] = None
    source_domain: Optional[str] = None
    title: str
    doc_type: str
    legal_status: str
    doc_number: Optional[str] = None
    doc_number_source: Optional[str] = None
    issue_date: Optional[date] = None
    issue_date_source: Optional[str] = None
    date_precision: str = "day"
    effective_date: Optional[date] = None
    category: str
    topics: List[str]
    law_version: Optional[str] = None
    url: str
    link_quality: str = "direct_document"
    ministry: Optional[str] = None
    pdf_url: Optional[str] = None
    content_text: Optional[str] = None
    text_status: str
    status: str
    status_confidence: Optional[float] = None
    supersedes_refs: List[str]
    hidden: bool = False
    hidden_reason: Optional[str] = None
    is_manual: bool = False
    manual_added_at: Optional[datetime] = None
    first_seen_at: datetime
    fetched_at: datetime
    updated_at: datetime
    backfilled: bool
    is_new: bool
    is_saved: bool
    ai_summary: Optional[Dict[str, Any]] = None
    ai_status: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class GovUpdatesListResponse(BaseModel):
    items: List[GovUpdateResponse]
    total: int
    page: int
    page_size: int
    facets: Dict[str, Dict[str, int]]


class GovCategorySourceItem(BaseModel):
    code: str
    name: str
    status: str
    enabled: bool
    last_error: Optional[str] = None


class GovMetaResponse(BaseModel):
    category_counts: Dict[str, int]
    total_updates: int
    last_sync_at: Optional[datetime] = None
    last_attempt_at: Optional[datetime] = None
    sources_total: int
    sources_ok: int
    sources_degraded: int
    sources_blocked: int
    sources_unreachable: int
    sources_disabled: int
    category_sources: Dict[str, List[GovCategorySourceItem]] = {}


class GovSourceToggleRequest(BaseModel):
    enabled: bool


class GovSyncRequest(BaseModel):
    source_code: Optional[str] = None
    backfill: bool = False
