"""
Client Router — full CRUD + sub-section endpoints.
All {client_id} path params are UUIDs.
"""

import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.models.user import User
from app.services.client_service import ClientService
from app.schemas.client import (
    ClientCardResponse,
    ClientCreate,
    ClientUpdate,
    ClientDashboardResponse,
    ClientOverviewResponse,
    ClientHistoryResponse,
)
from app.schemas.gst import GSTRecordResponse
from app.schemas.tax import TaxRecordResponse
from app.schemas.audit import AuditReportResponse
from app.schemas.invoice import InvoiceResponse
from app.schemas.document import DocumentResponse
from app.schemas.common import APIResponse, PaginatedResponse

router = APIRouter()


@router.post(
    "",
    response_model=APIResponse[ClientCardResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create client",
)
def create_client(
    data: ClientCreate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = ClientService(db)
    card = svc.create_client(data)
    return APIResponse(data=card, message=f"Client {card.id} created")


@router.get("", response_model=APIResponse[PaginatedResponse], summary="List clients")
def list_clients(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    search: Optional[str] = Query(None),
    sort_by: str = Query("created_at"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$"),
    status: Optional[str] = Query(None),
    risk_level: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    svc = ClientService(db)
    result = svc.get_clients(
        page=page,
        page_size=page_size,
        search=search,
        sort_by=sort_by,
        sort_order=sort_order,
        status=status,
        risk_level=risk_level,
    )
    return APIResponse(data=result, message="Clients retrieved")


@router.get(
    "/{client_id}",
    response_model=APIResponse[ClientDashboardResponse],
    summary="Full client dashboard",
)
def get_dashboard(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(
        data=ClientService(db).get_client_dashboard(client_id),
        message="Dashboard retrieved",
    )


@router.put(
    "/{client_id}",
    response_model=APIResponse[ClientCardResponse],
    summary="Update client",
)
def update_client(
    client_id: uuid.UUID,
    data: ClientUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    card = ClientService(db).update_client(client_id, data)
    return APIResponse(data=card, message=f"Client {card.id} updated")


@router.delete(
    "/{client_id}", response_model=APIResponse[dict], summary="Delete client"
)
def delete_client(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    result = ClientService(db).delete_client(client_id)
    return APIResponse(data=result, message=result["message"])


@router.get("/{client_id}/overview", response_model=APIResponse[ClientOverviewResponse])
def overview(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(
        data=ClientService(db).get_client_overview(client_id), message="OK"
    )


@router.get("/{client_id}/gst", response_model=APIResponse[List[GSTRecordResponse]])
def gst_records(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(data=ClientService(db).get_gst_records(client_id), message="OK")


@router.get("/{client_id}/tax", response_model=APIResponse[List[TaxRecordResponse]])
def tax_records(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(data=ClientService(db).get_tax_records(client_id), message="OK")


@router.get("/{client_id}/audit", response_model=APIResponse[List[AuditReportResponse]])
def audit_reports(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(
        data=ClientService(db).get_audit_reports(client_id), message="OK"
    )


@router.get("/{client_id}/invoices", response_model=APIResponse[List[InvoiceResponse]])
def invoices(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(data=ClientService(db).get_invoices(client_id), message="OK")


@router.get(
    "/{client_id}/documents", response_model=APIResponse[List[DocumentResponse]]
)
def documents(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(data=ClientService(db).get_documents(client_id), message="OK")


@router.get("/{client_id}/history", response_model=APIResponse[ClientHistoryResponse])
def history(
    client_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return APIResponse(data=ClientService(db).get_history(client_id), message="OK")
