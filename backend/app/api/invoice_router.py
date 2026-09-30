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
from typing import Optional, List, Any, Dict
from decimal import Decimal
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
from app.models.journal_entry import JournalEntry
from app.models.accounting_record import AccountingRecord
from app.schemas.uploaded_document import (
    UploadedDocumentResponse,
    UploadedDocumentListItem,
    DocumentUpdateRequest,
)
from app.schemas.common import APIResponse

logger = logging.getLogger(__name__)
settings = get_settings()
router = APIRouter()

UPLOAD_BASE = Path(settings.UPLOAD_DIR)


def _parse_decimal_safe(val: Any) -> Optional[Decimal]:
    """Safely parse currency/numeric strings to Decimal, stripping Rs, ₹, commas."""
    if val is None:
        return None
    s = str(val).strip()
    if not s or s.lower() in ("none", "null", "—", "-", "n/a"):
        return None
    cleaned = (
        s.replace("₹", "")
        .replace("Rs.", "")
        .replace("Rs", "")
        .replace("$", "")
        .replace(",", "")
        .strip()
    )
    if not cleaned:
        return None
    try:
        return Decimal(cleaned)
    except Exception:
        return None


def _build_metadata(
    metadata_json: Optional[str],
    field_verification: Optional[str],
    extraction_method: Optional[str] = None,
) -> Optional[str]:
    """Merge metadata_json, field_verification, and extraction_method into a single JSON string for the metadata_ column."""
    import json as _json
    result: dict = {}
    if metadata_json:
        try:
            parsed = _json.loads(metadata_json)
            result["fields"] = parsed
            if isinstance(parsed, dict):
                for k in ("table_data", "line_items", "line_item_headers"):
                    if k in parsed:
                        result[k] = parsed[k]
        except Exception:
            result["fields_raw"] = metadata_json
    if field_verification:
        try:
            result["field_verification"] = _json.loads(field_verification)
        except Exception:
            result["field_verification_raw"] = field_verification
    if extraction_method:
        result["extraction_method"] = extraction_method
    return _json.dumps(result) if result else None


def _has_table_data(metadata_json: Optional[str]) -> bool:
    """Return True if metadata_json contains table_data or line_items with at least one row."""
    import json as _json
    if not metadata_json:
        return False
    try:
        parsed = _json.loads(metadata_json)
        # Supports direct table_data, nested under "fields", and line_items
        td = parsed.get("table_data") or (parsed.get("fields") or {}).get("table_data")
        if td and isinstance(td, dict):
            rows = td.get("rows", [])
            if len(rows) > 0:
                return True
        li = parsed.get("line_items") or (parsed.get("fields") or {}).get("line_items")
        if isinstance(li, list) and len(li) > 0:
            return True
    except Exception:
        pass
    return False


def _count_meaningful_fields(**kwargs) -> int:
    """Count how many non-empty string/numeric fields are provided."""
    count = 0
    for v in kwargs.values():
        if v is not None and str(v).strip() not in ("", "None", "null"):
            count += 1
    return count


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
    # Extended: category-specific overflow fields (JSON string)
    metadata_json: Optional[str] = Form(default=None),
    # Per-field confidence/verification from OCR (JSON string)
    field_verification: Optional[str] = Form(default=None),
    # Extraction method from OCR pipeline (stored in metadata)
    extraction_method: Optional[str] = Form(default=None),
    # Force save even if a duplicate is detected
    force_save: Optional[str] = Form(default="false"),
    file: Optional[UploadFile] = File(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # ── Validate client exists ──
    from app.models.client import Client
    from app.services.document_validator import detect_duplicate
    import json as _json

    client = (
        db.query(Client)
        .filter(Client.id == client_id, Client.status != "deleted")
        .first()
    )
    if not client:
        raise NotFoundException(detail=f"Client {client_id} not found")

    if document_category == "document_list" and document_type == "scan":
        raise BadRequestException(
            detail="Document List category only supports file upload, not scanning."
        )

    _force_save = str(force_save or "false").lower() in ("true", "1", "yes")

    # ── Duplicate detection ──
    if not _force_save:
        dup = detect_duplicate(
            db=db,
            client_id=client_id,
            document_category=document_category,
            invoice_number=invoice_number,
            notice_number=notice_number,
            arn=arn,
        )
        if dup:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "duplicate_detected",
                    "duplicate": dup,
                    "message": (
                        "A document with the same identifier already exists for this client. "
                        "Submit with force_save=true to save anyway."
                    ),
                },
            )

    # ── Require attached file ──
    if not file or not file.filename or not file.filename.strip():
        raise BadRequestException(
            detail="A document file is required. Please select or upload a file first."
        )

    # ── Handle file ──
    file_path_str: Optional[str] = None
    file_name_str: Optional[str] = None
    file_size_str: Optional[str] = None
    file_ext: Optional[str] = None

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
    def _dec(v, field_name="Value"):
        if v is None or str(v).strip() == "":
            return None
        try:
            from decimal import Decimal
            val = Decimal(str(v).replace(",", "").strip())
            if val < 0 and document_category not in ["credit_note", "debit_note", "gst_return"]:
                raise BadRequestException(detail=f"{field_name} cannot be negative for category '{document_category}'")
            return val
        except Exception as e:
            if isinstance(e, BadRequestException):
                raise e
            raise BadRequestException(detail=f"Invalid numeric format for {field_name}: '{v}'")

    # ── Mandatory Identifiers ──
    # NOTE: For tabular/report documents (sales_records, purchase_records),
    # an invoice_number may legitimately be absent. We allow save when:
    #   a) At least one meaningful core field is present, OR
    #   b) metadata_json contains table_data with rows
    # Hard blocks are only kept for strict identifier categories.

    # Categories where a unique doc identifier is still required (not reports)
    # For e_way_bill and gst_challan the number IS the primary identifier (hard block).
    # For b2b_invoice, b2c_invoice, e_invoice: OCR often reads GSTIN/amount correctly
    # but misses the invoice number — allow save when at least one meaningful field exists.
    strict_identifier_categories = {"e_way_bill", "gst_challan"}

    if document_category in strict_identifier_categories:
        if not invoice_number or not str(invoice_number).strip():
            raise BadRequestException(detail=f"Document number is required for '{document_category}'")

    elif document_category in {"b2b_invoice", "b2c_invoice", "e_invoice"}:
        has_invoice = invoice_number and str(invoice_number).strip()
        has_gstin_val = gstin and str(gstin).strip()
        has_amount_val = amount and str(amount).strip()
        has_party = (vendor and str(vendor).strip()) or (customer and str(customer).strip())
        if not has_invoice and not has_gstin_val and not has_amount_val and not has_party:
            raise BadRequestException(
                detail=(
                    f"Document '{document_category}' requires at least one of: "
                    "invoice_number, GSTIN, amount, or party name."
                )
            )
    elif document_category in ("sales_records", "purchase_records", "credit_note", "debit_note"):
        # Allow saving reports/bulk documents without a single invoice_number
        # if meaningful fields or table rows are present
        has_invoice = invoice_number and str(invoice_number).strip()
        has_tables = _has_table_data(metadata_json)
        has_fields = _count_meaningful_fields(
            gstin=gstin, vendor=vendor, customer=customer, amount=amount,
            taxable_amount=taxable_amount, invoice_date=invoice_date,
        ) > 0
        if not has_invoice and not has_tables and not has_fields:
            raise BadRequestException(
                detail=(
                    f"Document '{document_category}' requires at least one of: "
                    "invoice_number, GSTIN, amount, or table rows."
                )
            )

    elif document_category == "gst_notice":
        if not notice_number or not str(notice_number).strip():
            raise BadRequestException(detail=f"Notice number is required for '{document_category}'")

    elif document_category == "gst_return":
        if not financial_year or not str(financial_year).strip():
            raise BadRequestException(detail=f"Financial year is required for '{document_category}'")

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
        amount=_dec(amount, "Amount"),
        taxable_amount=_dec(taxable_amount, "Taxable Amount"),
        cgst=_dec(cgst, "CGST"),
        sgst=_dec(sgst, "SGST"),
        igst=_dec(igst, "IGST"),
        cess=_dec(cess, "Cess"),
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
        ocr_status="done" if document_type == "scan" else "pending",
        status="pending",
        uploaded_by=current_user.email,
        metadata_=_build_metadata(metadata_json, field_verification, extraction_method),
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


# ── Get recent uploaded documents across CA clients ───────────
@router.get(
    "/recent",
    summary="Get recent uploaded documents across CA clients",
)
def get_recent_documents(
    limit: int = Query(default=10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.client import Client
    if current_user.role in ("ca", "admin"):
        clients = db.query(Client).filter(Client.user_id == current_user.id).all()
    else:
        clients = db.query(Client).filter(Client.email == current_user.email).all()
    client_map = {c.id: c for c in clients}
    if not client_map:
        return APIResponse(data=[], message="No documents found")
    docs = (
        db.query(UploadedDocument)
        .filter(UploadedDocument.client_id.in_(client_map.keys()))
        .order_by(UploadedDocument.uploaded_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for d in docs:
        c = client_map.get(d.client_id)
        result.append({
            "id": str(d.id),
            "client_id": str(d.client_id),
            "client_code": c.client_code if c else "",
            "company_name": c.company_name if c else "",
            "document_category": d.document_category,
            "document_type": d.document_type,
            "invoice_number": d.invoice_number,
            "vendor": d.vendor,
            "customer": d.customer,
            "amount": float(d.amount) if d.amount is not None else None,
            "status": d.status,
            "file_name": d.file_name,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "uploaded_by": d.uploaded_by,
        })
    return APIResponse(data=result, message=f"{len(result)} recent document(s) retrieved")


# ── Search documents across CA clients ─────────────────────────
@router.get(
    "/search",
    summary="Search uploaded documents across CA clients",
)
def search_documents(
    q: str = Query(..., min_length=1),
    limit: int = Query(default=20, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    from app.models.client import Client
    from sqlalchemy import or_
    if current_user.role in ("ca", "admin"):
        clients = db.query(Client).filter(Client.user_id == current_user.id).all()
    else:
        clients = db.query(Client).filter(Client.email == current_user.email).all()
    client_map = {c.id: c for c in clients}
    if not client_map:
        return APIResponse(data=[], message="No matching documents")
    term = f"%{q.strip()}%"
    docs = (
        db.query(UploadedDocument)
        .filter(
            UploadedDocument.client_id.in_(client_map.keys()),
            or_(
                UploadedDocument.invoice_number.ilike(term),
                UploadedDocument.file_name.ilike(term),
                UploadedDocument.vendor.ilike(term),
                UploadedDocument.customer.ilike(term),
                UploadedDocument.document_category.ilike(term),
                UploadedDocument.gstin.ilike(term),
            ),
        )
        .order_by(UploadedDocument.uploaded_at.desc())
        .limit(limit)
        .all()
    )
    result = []
    for d in docs:
        c = client_map.get(d.client_id)
        result.append({
            "id": str(d.id),
            "client_id": str(d.client_id),
            "client_code": c.client_code if c else "",
            "company_name": c.company_name if c else "",
            "document_category": d.document_category,
            "document_type": d.document_type,
            "invoice_number": d.invoice_number,
            "vendor": d.vendor,
            "customer": d.customer,
            "amount": float(d.amount) if d.amount is not None else None,
            "status": d.status,
            "file_name": d.file_name,
            "file_type": d.file_type,
            "file_size": d.file_size,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "uploaded_by": d.uploaded_by,
        })
    return APIResponse(data=result, message=f"{len(result)} match(es) found")


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
    # Security check: CA/admin can access any document; client users can access their own
    if current_user.role not in ("ca", "admin"):
        from app.models.client import Client
        from app.core.exceptions import ForbiddenException

        if doc.client_id:
            client = db.query(Client).filter(Client.id == doc.client_id).first()
            if client and current_user.email != client.email and current_user.email != doc.uploaded_by:
                raise ForbiddenException(detail="You do not have permission to download this document")
        elif current_user.email != doc.uploaded_by:
            raise ForbiddenException(detail="You do not have permission to download this document")

    path = Path(doc.file_path)
    if not path.is_absolute() and not path.exists():
        backend_dir = Path(__file__).resolve().parent.parent.parent
        if (backend_dir / doc.file_path).exists():
            path = backend_dir / doc.file_path
        elif (UPLOAD_BASE / path.name).exists():
            path = UPLOAD_BASE / path.name

    if not path.exists():
        raise NotFoundException(detail="File not found on server")

    import mimetypes
    media_type, _ = mimetypes.guess_type(doc.file_name or str(path))
    return FileResponse(
        path=str(path),
        filename=doc.file_name or path.name,
        media_type=media_type or "application/octet-stream",
    )


# ── Update / Edit document fields ──────────────────────────────
@router.patch(
    "/document/{doc_id}",
    response_model=APIResponse[UploadedDocumentResponse],
    summary="Update or edit document fields and metadata",
)
@router.put(
    "/document/{doc_id}",
    response_model=APIResponse[UploadedDocumentResponse],
    summary="Update or edit document fields and metadata",
)
def update_document(
    doc_id: uuid.UUID,
    payload: DocumentUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as _json

    doc = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
    if not doc:
        raise NotFoundException(detail=f"Document {doc_id} not found")

    existing_meta = {}
    if doc.metadata_:
        try:
            existing_meta = _json.loads(doc.metadata_)
        except Exception:
            existing_meta = {"raw": doc.metadata_}

    meta_fields = existing_meta.get("fields")
    if not isinstance(meta_fields, dict):
        meta_fields = {}

    if payload.fields is not None:
        raw_fields = payload.fields

        def _get_val(*keys):
            for k in keys:
                if k in raw_fields:
                    return raw_fields[k]
            return None

        def _is_provided(*keys):
            return any(k in raw_fields for k in keys)

        # Merge into metadata fields
        for k, v in raw_fields.items():
            if v is None or str(v).strip() == "":
                if k in meta_fields:
                    del meta_fields[k]
            else:
                meta_fields[k] = str(v).strip()

        # Update core financial fields
        num_mappings = [
            ("amount", ["amount", "total", "total_amount", "grand_total", "net_amount"]),
            ("taxable_amount", ["taxable_amount", "taxable_value", "assessable_value", "basic_amount"]),
            ("cgst", ["cgst", "cgst_amount", "central_tax", "central_gst"]),
            ("sgst", ["sgst", "sgst_amount", "state_tax", "state_gst"]),
            ("igst", ["igst", "igst_amount", "integrated_tax", "integrated_gst"]),
            ("cess", ["cess", "cess_amount", "compensation_cess"]),
        ]
        for col_name, aliases in num_mappings:
            if _is_provided(*aliases):
                val = _get_val(*aliases)
                if val is None or str(val).strip() == "":
                    setattr(doc, col_name, None)
                else:
                    dec_val = _parse_decimal_safe(val)
                    setattr(doc, col_name, dec_val)

        # Update core string fields
        str_mappings = [
            ("invoice_number", ["invoice_number", "invoice_no", "inv_no", "bill_no", "bill_number", "doc_no", "document_no"]),
            ("invoice_date", ["invoice_date", "date", "bill_date", "inv_date", "posting_date"]),
            ("vendor", ["vendor", "vendor_name", "supplier", "supplier_name", "seller", "seller_name", "company_name"]),
            ("customer", ["customer", "customer_name", "buyer", "buyer_name", "recipient", "client"]),
            ("gstin", ["gstin", "supplier_gstin", "seller_gstin", "vendor_gstin", "gst_no"]),
            ("hsn", ["hsn", "hsn_code", "hsn_sac", "sac"]),
            ("arn", ["arn", "acknowledgement_number_arn"]),
            ("notice_number", ["notice_number", "notice_no"]),
            ("notice_date", ["notice_date", "date_of_notice"]),
            ("response_due_date", ["response_due_date", "due_date", "reply_by"]),
            ("priority", ["priority"]),
            ("gst_return_type", ["gst_return_type", "return_type"]),
            ("financial_year", ["financial_year", "fy"]),
            ("month", ["month", "quarter"]),
            ("filed_date", ["filed_date", "filing_date"]),
        ]
        for col_name, aliases in str_mappings:
            if _is_provided(*aliases):
                val = _get_val(*aliases)
                if val is None or str(val).strip() == "":
                    setattr(doc, col_name, None)
                else:
                    cleaned_str = str(val).strip()
                    if col_name == "gstin":
                        cleaned_str = cleaned_str.upper()
                    setattr(doc, col_name, cleaned_str)

    if payload.status is not None:
        doc.status = payload.status
    if payload.document_category is not None:
        doc.document_category = payload.document_category
    if payload.applies_to is not None:
        doc.applies_to = payload.applies_to.strip().lower()

    existing_meta["fields"] = meta_fields
    doc.metadata_ = _json.dumps(existing_meta)

    db.commit()
    db.refresh(doc)

    logger.info("Document updated: %s", doc.id)
    return APIResponse(
        data=UploadedDocumentResponse.model_validate(doc),
        message="Document updated successfully",
    )


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

    # Prevent deleting a document that has a posted entry
    posted_je = db.query(JournalEntry).filter(
        JournalEntry.document_id == doc_id,
        JournalEntry.status == "posted",
    ).first()
    if posted_je:
        raise BadRequestException(
            detail=f"Cannot delete document with a posted ledger entry (document {doc_id}): it is linked to posted Journal Entry #{posted_je.entry_number}. "
                   f"The entry must be reversed before deleting this source document."
        )

    posted_rec = db.query(AccountingRecord).filter(
        AccountingRecord.document_id == doc_id,
        AccountingRecord.status == "posted",
    ).first()
    if posted_rec:
        raise BadRequestException(
            detail=f"Cannot delete document with a posted ledger entry (document {doc_id}): it is linked to a posted voucher record. "
                   f"The entry must be reversed before deleting this source document."
        )

    # Remove file from disk
    if doc.file_path:
        try:
            Path(doc.file_path).unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Could not delete file %s: %s", doc.file_path, e)
    db.delete(doc)
    db.commit()
    return APIResponse(data={"id": str(doc_id)}, message="Document deleted")


# ── Reprocess & Extract Line Items on Demand ────────────────────
@router.post(
    "/document/{doc_id}/extract-items",
    response_model=APIResponse[UploadedDocumentResponse],
    summary="Extract product line items for an existing document",
)
def extract_document_line_items(
    doc_id: uuid.UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    import json as _json
    from app.api.routers.ocr.router import _gemini_vision_extract

    doc = db.query(UploadedDocument).filter(UploadedDocument.id == doc_id).first()
    if not doc:
        raise NotFoundException(detail=f"Document {doc_id} not found")

    if not doc.file_path:
        raise HTTPException(status_code=400, detail="No file available for this document.")

    path = Path(doc.file_path)
    if not path.exists():
        raise NotFoundException(detail="Document file not found on disk.")

    with open(path, "rb") as f:
        content = f.read()

    fields, line_items = _gemini_vision_extract(content, doc.document_category)

    # Merge into existing metadata
    existing_meta = {}
    if doc.metadata_:
        try:
            existing_meta = _json.loads(doc.metadata_)
        except Exception:
            existing_meta = {"raw": doc.metadata_}

    if line_items:
        existing_meta["line_items"] = line_items
        col_labels = {
            "sr_no": "Sr. No.",
            "item_name": "Item Description",
            "company_name": "Company / Brand",
            "hsn": "HSN / SAC",
            "batch_no": "Batch No.",
            "expiry_date": "Expiry Date",
            "quantity": "Quantity",
            "rate": "Rate / Price",
            "discount": "Discount",
            "taxable_amount": "Taxable Value",
            "cgst_amount": "CGST",
            "sgst_amount": "SGST",
            "igst_amount": "IGST",
            "total_amount": "Total Amount",
        }
        preferred_order = [
            "sr_no", "item_name", "company_name", "hsn", "batch_no", "expiry_date",
            "quantity", "rate", "discount", "taxable_amount", "cgst_amount", "sgst_amount", "igst_amount", "total_amount"
        ]
        active_cols = [c for c in preferred_order if any(c in row for row in line_items)]
        for row in line_items:
            for k in row.keys():
                if k not in active_cols:
                    active_cols.append(k)
        raw_headers = [col_labels.get(c, c.replace("_", " ").title()) for c in active_cols]

        enriched_rows = []
        for row in line_items:
            er = dict(row)
            for c, rh in zip(active_cols, raw_headers):
                if c in row and rh not in er:
                    er[rh] = row[c]
                elif rh in row and c not in er:
                    er[c] = row[rh]
            enriched_rows.append(er)

        existing_meta["table_data"] = {
            "headers": active_cols,
            "headers_raw": raw_headers,
            "rows": enriched_rows,
        }
        existing_meta["line_item_headers"] = raw_headers
        existing_meta["line_items"] = enriched_rows

    # Store HSN Summary breakdown if available
    hsn_summary = fields.get("hsn_summary")
    if hsn_summary and isinstance(hsn_summary, list):
        existing_meta["hsn_summary"] = hsn_summary

    # Ensure existing_meta["fields"] contains all extracted document-level fields
    meta_fields = existing_meta.get("fields")
    if not isinstance(meta_fields, dict):
        meta_fields = {}
    for k, v in fields.items():
        if k != "hsn_summary" and v is not None and str(v).strip():
            meta_fields[k] = str(v).strip()
    existing_meta["fields"] = meta_fields

    # Update core calculation and financial fields from vision extraction (priority for totals on the last page)
    for k in ("amount", "taxable_amount", "cgst", "sgst", "igst", "cess"):
        if k in fields and fields[k] is not None:
            try:
                dec_val = _parse_decimal_safe(fields[k])
                if dec_val is not None and hasattr(doc, k):
                    setattr(doc, k, dec_val)
            except Exception:
                pass

    for k in ("vendor", "customer", "invoice_number", "invoice_date", "hsn", "gstin"):
        if k in fields and fields[k] and hasattr(doc, k):
            curr_val = getattr(doc, k)
            if not curr_val or curr_val in ("0", "No", "No.", "(Bill to)", "Bill to"):
                setattr(doc, k, str(fields[k]))

    doc.metadata_ = _json.dumps(existing_meta)
    db.commit()
    db.refresh(doc)
    msg = f"Extracted {len(line_items)} line items"
    if hsn_summary and isinstance(hsn_summary, list):
        msg += f" and {len(hsn_summary)} HSN summary entries"
    return APIResponse(data=UploadedDocumentResponse.model_validate(doc), message=msg)
