"""
Government Updates API Router.
Mounted under /api/v1/gov-updates.
All endpoints require authentication; admin/CA endpoints guarded by require_ca_role.
"""

import uuid
from typing import Optional, List
from datetime import date
from fastapi import APIRouter, Depends, Query, Path, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user, require_ca_role
from app.models.user import User
from app.schemas.government_update import (
    GovUpdatesListResponse,
    GovUpdateResponse,
    GovMetaResponse,
    GovSourceResponse,
    GovSourceToggleRequest,
    GovSyncRequest,
)
from app.services.gov_updates.service import GovUpdateService

router = APIRouter()


@router.get("", response_model=GovUpdatesListResponse, summary="List Government Updates with filters & facets")
def list_gov_updates(
    category: Optional[str] = Query(None, description="Category filter (All, GST, Income Tax, Budget, Accounting, etc.)"),
    source: Optional[str] = Query(None, description="Source code filter"),
    doc_type: Optional[str] = Query(None, description="Document type filter"),
    law_version: Optional[str] = Query(None, description="Law version filter"),
    topic: Optional[str] = Query(None, description="Topic taxonomy filter"),
    status: Optional[str] = Query(None, description="Status filter (active, superseded, withdrawn)"),
    legal_status: Optional[str] = Query(None, description="Legal status filter"),
    date_from: Optional[date] = Query(None, description="Issue date from (ISO 8601)"),
    date_to: Optional[date] = Query(None, description="Issue date to (ISO 8601)"),
    q: Optional[str] = Query(None, description="Full-text search query across title, text, doc number"),
    saved: bool = Query(False, description="Filter only saved bookmarks for current user"),
    include_archive: bool = Query(True, description="Include non-active/superseded updates"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return GovUpdateService.list_updates(
        db=db,
        user=current_user,
        category=category,
        source_code=source,
        doc_type=doc_type,
        law_version=law_version,
        topic=topic,
        status=status,
        legal_status=legal_status,
        date_from=date_from,
        date_to=date_to,
        q=q,
        saved_only=saved,
        include_archive=include_archive,
        page=page,
        page_size=page_size,
    )


@router.get("/meta", response_model=GovMetaResponse, summary="Get summary metadata, category counts and source health")
def get_gov_meta(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return GovUpdateService.get_meta(db=db)


@router.get("/sources", response_model=List[GovSourceResponse], summary="List all government sources with health status (Admin/CA)")
def list_gov_sources(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ca_role),
):
    return GovUpdateService.list_sources(db=db)


@router.patch("/sources/{source_id}", response_model=GovSourceResponse, summary="Enable or disable a source (Admin/CA)")
def toggle_gov_source(
    source_id: uuid.UUID = Path(..., description="Source ID"),
    payload: GovSourceToggleRequest = ...,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ca_role),
):
    updated = GovUpdateService.toggle_source(db=db, source_id=source_id, enabled=payload.enabled)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Source not found")
    return updated


@router.post("/sync", summary="Trigger manual sync of government updates (Admin/CA)")
def trigger_gov_sync(
    payload: GovSyncRequest = GovSyncRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_ca_role),
):
    result = GovUpdateService.trigger_sync(db=db, source_code=payload.source_code, backfill=payload.backfill)
    return {"message": "Sync complete", "details": result}


@router.get("/{update_id}", response_model=GovUpdateResponse, summary="Get single government update detail")
def get_gov_update(
    update_id: uuid.UUID = Path(..., description="Update ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    update = GovUpdateService.get_update_by_id(db=db, user=current_user, update_id=update_id)
    if not update:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Government update not found")
    return update


@router.post("/{update_id}/save", summary="Bookmark / save an update for current user")
def save_gov_update(
    update_id: uuid.UUID = Path(..., description="Update ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    success = GovUpdateService.save_update(db=db, user=current_user, update_id=update_id)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Government update not found")
    return {"status": "saved", "update_id": str(update_id)}


@router.delete("/{update_id}/save", summary="Remove bookmark / unsave an update")
def unsave_gov_update(
    update_id: uuid.UUID = Path(..., description="Update ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    GovUpdateService.unsave_update(db=db, user=current_user, update_id=update_id)
    return {"status": "unsaved", "update_id": str(update_id)}


@router.post("/{update_id}/unsave", summary="Alternative POST endpoint to unsave an update")
def unsave_gov_update_post(
    update_id: uuid.UUID = Path(..., description="Update ID"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    GovUpdateService.unsave_update(db=db, user=current_user, update_id=update_id)
    return {"status": "unsaved", "update_id": str(update_id)}
