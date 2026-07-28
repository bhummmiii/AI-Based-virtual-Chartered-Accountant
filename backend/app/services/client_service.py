"""
Client Service — business logic for Workspace module.
All models use UUID PKs. Field maps translate between
frontend title-case values and DB lowercase values.
"""
import logging, math
from datetime import datetime, timezone, date, timedelta
from decimal import Decimal
from typing import Optional, List

from sqlalchemy.orm import Session

from app.repositories.client_repository import ClientRepository
from app.core.exceptions import NotFoundException, ConflictException
from app.models.client import Client
from app.models.gst_record import GSTRecord
from app.models.tax_record import TaxRecord
from app.models.audit_report import AuditReport
from app.schemas.client import (
    ClientCardResponse, ClientCreate, ClientUpdate,
    ClientResponse, ClientDashboardResponse, ClientOverviewResponse,
    ClientHistoryResponse, ActivityItem,
)
from app.schemas.accounting import AccountingRecordResponse
from app.schemas.gst import GSTRecordResponse
from app.schemas.tax import TaxRecordResponse
from app.schemas.audit import AuditReportResponse
from app.schemas.invoice import InvoiceResponse
from app.schemas.document import DocumentResponse
from app.schemas.common import PaginatedResponse

logger = logging.getLogger(__name__)

# ── Value maps ─────────────────────────────────────────────────
S_FE2DB = {"Active":"active","Review":"pending","Inactive":"inactive","Pending":"pending"}
S_DB2FE = {"active":"Active","pending":"Review","inactive":"Inactive","deleted":"Inactive"}
R_FE2DB = {"Low":"low","Medium":"medium","High":"high"}
R_DB2FE = {"low":"Low","medium":"Medium","high":"High"}
T_FE2DB = {"Company":"company","Individual":"individual","LLP":"llp","Partnership":"partnership"}
T_DB2FE = {"company":"Company","individual":"Individual","llp":"LLP","partnership":"Partnership"}
G_FE2DB = {"Filed":"filed","Due":"pending","Overdue":"overdue"}
G_DB2FE = {"filed":"Filed","pending":"Due","overdue":"Overdue","exempt":"Filed",None:"Pending"}
A_FE2DB = {"Passed":"completed","In Progress":"in_progress","Pending":"pending","Flagged":"flagged"}
A_DB2FE = {"completed":"Passed","in_progress":"In Progress","pending":"Pending","flagged":"Flagged",None:"Pending"}


def _initials(name: str) -> str:
    words = name.strip().split()
    return "".join(w[0].upper() for w in words if w and w[0].isalpha())[:2] or "??"


def _rel_time(dt: datetime) -> str:
    if not dt: return "Recently"
    if not dt.tzinfo: dt = dt.replace(tzinfo=timezone.utc)
    s = int((datetime.now(timezone.utc) - dt).total_seconds())
    if s < 60:    return "Just now"
    if s < 3600:  return f"{s//60} min ago"
    if s < 86400: return f"{s//3600} hour{'s' if s//3600!=1 else ''} ago"
    if s < 172800: return "Yesterday"
    d = s // 86400
    if d < 30: return f"{d} days ago"
    return dt.strftime("%d %b %Y")


def _next_code(repo: ClientRepository) -> str:
    return f"C-{repo.get_max_code_sequence() + 1}"


class ClientService:

    def __init__(self, db: Session):
        self.repo = ClientRepository(db)

    # ── CREATE ─────────────────────────────────────────────────
    def create_client(self, data: ClientCreate) -> ClientCardResponse:
        # Duplicate checks
        ex = self.repo.get_by_company_name(data.company)
        if ex and ex.status != "deleted":
            raise ConflictException(detail=f"'{data.company}' already exists ({ex.client_code})")
        if data.gstin:
            dup = self.repo.get_by_gst(data.gstin)
            if dup and dup.status != "deleted":
                raise ConflictException(detail=f"GSTIN {data.gstin} belongs to {dup.company_name}")
        if data.pan:
            dup = self.repo.get_by_pan(data.pan)
            if dup and dup.status != "deleted":
                raise ConflictException(detail=f"PAN {data.pan} belongs to {dup.company_name}")

        client = Client(
            client_code=_next_code(self.repo),
            company_name=data.company.strip(),
            contact_person=data.name.strip(),
            client_type=T_FE2DB.get(data.type, "company"),
            gst_number=data.gstin,
            pan_number=data.pan,
            email=data.email,
            phone=data.phone,
            address=data.address,
            city=data.city,
            state=data.state,
            country=data.country or "India",
            status=S_FE2DB.get(data.status, "active"),
            risk_level=R_FE2DB.get(data.risk, "low"),
        )
        client = self.repo.create(client)

        # Seed initial GST record
        self.repo.db.add(GSTRecord(
            client_id=client.id,
            gst_period=date.today().strftime("%Y-%m"),
            gst_type="GSTR-3B",
            taxable_amount=Decimal(str(data.revenue)),
            cgst=Decimal("0"), sgst=Decimal("0"), igst=Decimal("0"),
            total_tax=Decimal("0"),
            filing_status=G_FE2DB.get(data.gst, "pending"),
            due_date=date.today() + timedelta(days=20),
        ))
        # Seed initial Tax record
        self.repo.db.add(TaxRecord(
            client_id=client.id,
            financial_year="2025-26",
            tax_type="income_tax",
            taxable_income=Decimal(str(data.revenue)),
            tds=Decimal("0"), advance_tax=Decimal("0"), total_tax=Decimal("0"),
            status=G_FE2DB.get(data.tax, "pending"),
        ))
        # Seed initial Audit report
        self.repo.db.add(AuditReport(
            client_id=client.id,
            audit_type="statutory",
            audit_status=A_FE2DB.get(data.audit, "pending"),
            findings="Initial audit record — client onboarded.",
            recommendations="Complete KYC and submit first year documents.",
        ))
        self.repo.db.commit()

        logger.info("Created client %s — %s", client.client_code, client.company_name)
        return self._card(client,
                          G_FE2DB.get(data.gst, "pending"),
                          G_FE2DB.get(data.tax, "pending"),
                          A_FE2DB.get(data.audit, "pending"))

    # ── LIST ───────────────────────────────────────────────────
    def get_clients(self, page=1, page_size=50, search=None,
                    sort_by="created_at", sort_order="desc",
                    status=None, risk_level=None) -> PaginatedResponse:
        db_status = S_FE2DB.get(status, status.lower() if status else None)
        db_risk   = R_FE2DB.get(risk_level, risk_level.lower() if risk_level else None)
        if db_status == "deleted": db_status = None

        clients, total = self.repo.get_all(
            page=page, page_size=page_size, search=search,
            sort_by=sort_by, sort_order=sort_order,
            status_filter=db_status, risk_filter=db_risk,
        )
        cards = [
            self._card(c,
                       self.repo.get_latest_gst_status(c.id),
                       self.repo.get_latest_tax_status(c.id),
                       self.repo.get_latest_audit_status(c.id))
            for c in clients
        ]
        return PaginatedResponse(items=cards, total=total, page=page,
                                 page_size=page_size,
                                 total_pages=math.ceil(total/page_size) if page_size else 0)

    # ── DASHBOARD ──────────────────────────────────────────────
    def get_client_dashboard(self, client_id) -> ClientDashboardResponse:
        client = self.repo.get_full_dashboard(client_id)
        if not client or client.status == "deleted":
            raise NotFoundException(detail=f"Client {client_id} not found")
        return ClientDashboardResponse(
            client=ClientResponse.model_validate(client),
            gst=[GSTRecordResponse.model_validate(r) for r in client.gst_records],
            tax=[TaxRecordResponse.model_validate(r) for r in client.tax_records],
            audit=[AuditReportResponse.model_validate(r) for r in client.audit_reports],
            invoices=[InvoiceResponse.model_validate(r) for r in client.invoices],
            documents=[DocumentResponse.model_validate(r) for r in client.documents],
            accounting=[AccountingRecordResponse.model_validate(r) for r in client.accounting_records],
        )

    # ── OVERVIEW ───────────────────────────────────────────────
    def get_client_overview(self, client_id) -> ClientOverviewResponse:
        client = self._get_or_404(client_id)
        return ClientOverviewResponse(
            client_id=str(client.id),
            company_name=client.company_name,
            risk_level=R_DB2FE.get(client.risk_level, "Low"),
            compliance_status=self._compliance(
                self.repo.get_latest_gst_status(client.id),
                self.repo.get_latest_tax_status(client.id),
                self.repo.get_latest_audit_status(client.id),
            ),
            gst_status=G_DB2FE.get(self.repo.get_latest_gst_status(client.id), "Pending"),
            tax_status=G_DB2FE.get(self.repo.get_latest_tax_status(client.id), "Pending"),
            audit_status=A_DB2FE.get(self.repo.get_latest_audit_status(client.id), "Pending"),
        )

    # ── UPDATE ─────────────────────────────────────────────────
    def update_client(self, client_id, data: ClientUpdate) -> ClientCardResponse:
        client = self._get_or_404(client_id)
        patch = {}
        if data.company is not None:
            ex = self.repo.get_by_company_name(data.company)
            if ex and str(ex.id) != str(client_id) and ex.status != "deleted":
                raise ConflictException(detail=f"'{data.company}' already exists")
            patch["company_name"] = data.company.strip()
        if data.name    is not None: patch["contact_person"] = data.name.strip()
        if data.type    is not None: patch["client_type"] = T_FE2DB.get(data.type, data.type.lower())
        if data.status  is not None: patch["status"] = S_FE2DB.get(data.status, data.status.lower())
        if data.risk    is not None: patch["risk_level"] = R_FE2DB.get(data.risk, data.risk.lower())
        if data.gstin   is not None: patch["gst_number"] = data.gstin
        if data.pan     is not None: patch["pan_number"] = data.pan
        if data.email   is not None: patch["email"] = data.email
        if data.phone   is not None: patch["phone"] = data.phone
        if data.address  is not None: patch["address"] = data.address
        if data.city     is not None: patch["city"] = data.city
        if data.state    is not None: patch["state"] = data.state
        if data.country  is not None: patch["country"] = data.country
        client = self.repo.update(client, patch)
        return self._card(client,
                          self.repo.get_latest_gst_status(client.id),
                          self.repo.get_latest_tax_status(client.id),
                          self.repo.get_latest_audit_status(client.id))

    # ── DELETE ─────────────────────────────────────────────────
    def delete_client(self, client_id) -> dict:
        client = self._get_or_404(client_id)
        self.repo.soft_delete(client)
        return {"message": f"Client {client.client_code} deleted"}

    # ── SUB-SECTIONS ───────────────────────────────────────────
    def get_gst_records(self, cid):
        self._get_or_404(cid)
        return [GSTRecordResponse.model_validate(r) for r in self.repo.get_gst_records(cid)]

    def get_tax_records(self, cid):
        self._get_or_404(cid)
        return [TaxRecordResponse.model_validate(r) for r in self.repo.get_tax_records(cid)]

    def get_audit_reports(self, cid):
        self._get_or_404(cid)
        return [AuditReportResponse.model_validate(r) for r in self.repo.get_audit_reports(cid)]

    def get_invoices(self, cid):
        self._get_or_404(cid)
        return [InvoiceResponse.model_validate(r) for r in self.repo.get_invoices(cid)]

    def get_documents(self, cid):
        self._get_or_404(cid)
        return [DocumentResponse.model_validate(r) for r in self.repo.get_documents(cid)]

    def get_history(self, cid) -> ClientHistoryResponse:
        self._get_or_404(cid)
        items: List[ActivityItem] = []
        for r in self.repo.get_gst_records(cid):
            items.append(ActivityItem(id=str(r.id), type="gst",
                title=f"GST {r.gst_type}", description=f"Period {r.gst_period} — {r.filing_status}",
                date=r.created_at, status=r.filing_status))
        for r in self.repo.get_tax_records(cid):
            items.append(ActivityItem(id=str(r.id), type="tax",
                title=f"Tax — {r.tax_type}", description=f"FY {r.financial_year} — {r.status}",
                date=r.created_at, status=r.status))
        for r in self.repo.get_audit_reports(cid):
            items.append(ActivityItem(id=str(r.id), type="audit",
                title=f"{r.audit_type.title()} Audit", description=f"Status: {r.audit_status}",
                date=r.created_at, status=r.audit_status))
        for r in self.repo.get_invoices(cid):
            items.append(ActivityItem(id=str(r.id), type="invoice",
                title=f"Invoice {r.invoice_number}", description=f"{r.vendor_name} — ₹{r.amount:,.0f}",
                date=r.created_at, status=None))
        for r in self.repo.get_documents(cid):
            items.append(ActivityItem(id=str(r.id), type="document",
                title=r.file_name, description=f"Type: {r.file_type}",
                date=r.uploaded_at, status=None))
        items.sort(key=lambda x: x.date, reverse=True)
        return ClientHistoryResponse(client_id=str(cid), activities=items)

    # ── HELPERS ────────────────────────────────────────────────
    def _get_or_404(self, client_id) -> Client:
        c = self.repo.get_by_id(client_id)
        if not c or c.status == "deleted":
            raise NotFoundException(detail=f"Client {client_id} not found")
        return c

    def _card(self, client: Client, gst_s, tax_s, audit_s) -> ClientCardResponse:
        return ClientCardResponse(
            id=client.client_code,
            name=client.contact_person,
            company=client.company_name,
            type=T_DB2FE.get(client.client_type, client.client_type.title()),
            gstin=client.gst_number,
            revenue=0.0,
            status=S_DB2FE.get(client.status, "Active"),
            gst=G_DB2FE.get(gst_s, "Pending"),
            audit=A_DB2FE.get(audit_s, "Pending"),
            tax=G_DB2FE.get(tax_s, "Pending"),
            risk=R_DB2FE.get(client.risk_level, "Low"),
            lastActivity=_rel_time(client.updated_at),
            avatar=_initials(client.company_name),
            db_id=str(client.id),
        )

    @staticmethod
    def _compliance(gst, tax, audit) -> str:
        ss = [gst, tax, audit]
        if any(s == "overdue" for s in ss): return "non_compliant"
        if any(s in ("pending","in_progress") for s in ss): return "partially_compliant"
        return "compliant"
