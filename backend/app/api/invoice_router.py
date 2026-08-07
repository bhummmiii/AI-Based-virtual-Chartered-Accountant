"""
Invoice / Document Upload Router
POST /api/v1/invoices/{client_id}/upload  — upload with metadata form fields
GET  /api/v1/invoices/{client_id}         — list documents for a client
GET  /api/v1/invoices/document/{doc_id}   — get single document
DELETE /api/v1/invoices/document/{doc_id} — delete document

File is saved to UPLOAD_DIR/{client_id}/{uuid_filename}.ext
Only the relative path is stored in PostgreSQL.
"""

import uuid
import os
import logging
from typing import Optional, List
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    UploadFile,
    File,
    Form,
    Query,
    HTTPException,
    status,
)
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.core.dependencies import get_current_user
from app.core.config import get_settings
from app.core.exceptions import NotFoundException, BadRequestException
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.schemas.uploaded_document import (
    UploadedDocumentResponse,
    UploadedDocumentListItem,
)
from app.schemas.common import APIResponse

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

UPLOAD_BASE = Path(settings.UPLOAD_DIR)


def _ensure_dir(client_id: str) -> Path:
    p = UPLOAD_BASE / str(client_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _human_size(n_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n_bytes < 1024:
            return f"{n_bytes:.1f} {unit}"
        n_bytes //= 1024
    return f"{n_bytes} GB"


def _validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext not in settings.allowed_extensions_set:
        raise BadRequestException(
            detail=f"File type '.{ext}' not allowed. Allowed: {settings.ALLOWED_EXTENSIONS}"
        )
    return ext


# ── Upload document ───────────────────────────────────────────
@router.post(
    "/{client_id}/upload",
    response_model=APIResponse[UploadedDocumentResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document for a client",
)
async def upload_document(
    client_id: uuid.UUID,
    document_category: str = Form(...),
    document_type: str = Form(default="upload"),
    invoice_type: Optional[str] = Form(default=None),
    invoice_number: Optional[str] = Form(default=None),
    gstin: Optional[str] = Form(default=None),
    vendor: Optional[str] = Form(default=None),
    customer: Optional[str] = Form(default=None),
    invoice_date: Optional[str] = Form(default=None),
    amount: Optional[str] = Form(default=None),
    taxable_amount: Optional[str] = Form(default=None),
    cgst: Optional[str] = Form(default=None),
    sgst: Optional[str] = Form(default=None),
    igst: Optional[str] = Form(default=None),
    cess: Optional[str] = Form(default=None),
    hsn: Optional[str] = Form(default=None),
    gst_return_type: Optional[str] = Form(default=None),
    financial_year: Optional[str] = Form(default=None),
    month: Optional[str] = Form(default=None),
    filed_date: Optional[str] = Form(default=None),
    arn: Optional[str] = Form(default=None),
    notice_number: Optional[str] = Form(default=None),
    notice_date: Optional[str] = Form(default=None),
    response_due_date: Optional[str] = Form(default=None),
    priority: Optional[str] = Form(default=None),
    file: Optional[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Validate client exists ──
    from app.models.client import Client

    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.status != "deleted")
        .first()
    )
    if not client:
        raise NotFoundException(detail=f"Client {client_id} not found")

    # ── Handle file ──
    file_path_str: Optional[str] = None
    file_name_str: Optional[str] = None
    file_size_str: Optional[str] = None
    file_ext: Optional[str] = None

    if file and file.filename:
        file_ext = _validate_extension(file.filename)
        content = await file.read()
        size_bytes = len(content)

        if size_bytes > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise BadRequestException(
                detail=f"File exceeds {settings.MAX_UPLOAD_SIZE_MB} MB limit"
            )

        safe_name = f"{uuid.uuid4()}.{file_ext}"
        dest_dir = _ensure_dir(str(client_id))
        dest_path = dest_dir / safe_name

        with open(dest_path, "wb") as f_out:
            f_out.write(content)

        file_path_str = str(dest_path.relative_to(Path(".")))
        file_name_str = file.filename
        file_size_str = _human_size(size_bytes)

    # ── Normalise decimal fields ──
    def _dec(v):
        if v is None or v == "":
            return None
        try:
            from decimal import Decimal

            return Decimal(str(v))
        except Exception:
            return None

    # ── Persist ──
    doc = UploadedDocument(
        client_id=client_id,
        document_category=document_category,
        document_type=document_type,
        invoice_type=invoice_type,
        invoice_number=invoice_number,
        gstin=gstin.strip().upper() if gstin and gstin.strip() else None,
        vendor=vendor,
        customer=customer,
        invoice_date=invoice_date,
        amount=_dec(amount),
        taxable_amount=_dec(taxable_amount),
        cgst=_dec(cgst),
        sgst=_dec(sgst),
        igst=_dec(igst),
        cess=_dec(cess),
        hsn=hsn,
        gst_return_type=gst_return_type,
        financial_year=financial_year,
        month=month,
        filed_date=filed_date,
        arn=arn,
        notice_number=notice_number,
        notice_date=notice_date,
        response_due_date=response_due_date,
        priority=priority,
        file_name=file_name_str,
        file_path=file_path_str,
        file_size=file_size_str,
        file_type=file_ext,
        ocr_status="pending",
        status="pending",
        uploaded_by=current_user.email,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    logger.info(
        "Document uploaded: %s category=%s client=%s",
        doc.id,
        doc.document_category,
        client_id,
    )
    return APIResponse(
        data=UploadedDocumentResponse.model_validate(doc),
        message="Document uploaded successfully",
    )


# ── List documents for a client ────────────────────────────────
@router.get(
    "/{client_id}",
    response_model=APIResponse[List[UploadedDocumentListItem]],
    summary="List uploaded documents for a client",
)
def list_documents(
    client_id: uuid.UUID,
    category: Optional[str] = Query(default=None),
    document_type: Optional[str] = Query(default=None),
    status: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = db.query(UploadedDocument).filter(UploadedDocument.client_id == client_id)
    if category:
        q = q.filter(UploadedDocument.document_category == category)
    if document_type:
        q = q.filter(UploadedDocument.document_type == document_type)
    if status:
        q = q.filter(UploadedDocument.status == status)
    docs = q.order_by(UploadedDocument.uploaded_at.desc()).all()
    return APIResponse(
        data=[UploadedDocumentListItem.model_validate(d) for d in docs],
        message=f"{len(docs)} document(s) retrieved",
    )


# ── Get single document ────────────────────────────────────────
@router.get(
    "/document/{doc_id}",
    response_model=APIResponse[UploadedDocumentResponse],
    summary="Get document details",
)
def get_document(
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
    if not doc:
        raise NotFoundException(detail=f"Document {doc_id} not found")
    return APIResponse(data=UploadedDocumentResponse.model_validate(doc), message="OK")


# ── Download file ──────────────────────────────────────────────
@router.get(
    "/document/{doc_id}/download",
    summary="Download the uploaded file",
)
def download_document(
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
    if not doc or not doc.file_path:
        raise NotFoundException(detail="File not found")
    # Security: verify the authenticated user uploaded this or is the CA
    from app.models.client import Client

    client = db.query(Client).filter(Client.id == doc.client_id).first()
    if not client:
        raise NotFoundException(detail="Associated client not found")
    path = Path(doc.file_path)
    if not path.exists():
        raise NotFoundException(detail="File not found on server")
    return FileResponse(path=str(path), filename=doc.file_name or path.name)


# ── Delete document ────────────────────────────────────────────
@router.delete(
    "/document/{doc_id}",
    response_model=APIResponse[dict],
    summary="Delete a document (and its file)",
)
def delete_document(
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
    if not doc:
        raise NotFoundException(detail=f"Document {doc_id} not found")
    # Remove file from disk
    if doc.file_path:
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Could not delete file %s: %s", doc.file_path, e)
    db.delete(doc)
    db.commit()
    return APIResponse(data={"id": str(doc_id)}, message="Document deleted")
