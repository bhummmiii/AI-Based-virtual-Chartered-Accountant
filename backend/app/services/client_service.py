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
    ClientCardResponse,
    ClientCreate,
    ClientUpdate,
    ClientResponse,
    ClientDashboardResponse,
    ClientOverviewResponse,
    ClientHistoryResponse,
    ActivityItem,
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
S_FE2DB = {
    "Active": "active",
    "Review": "pending",
    "Inactive": "inactive",
    "Pending": "pending",
}
S_DB2FE = {
    "active": "Active",
    "pending": "Review",
    "inactive": "Inactive",
    "deleted": "Inactive",
}
R_FE2DB = {"Low": "low", "Medium": "medium", "High": "high"}
R_DB2FE = {"low": "Low", "medium": "Medium", "high": "High"}
T_FE2DB = {
    "Company": "company",
    "Individual": "individual",
    "LLP": "llp",
    "Partnership": "partnership",
}
T_DB2FE = {
    "company": "Company",
    "individual": "Individual",
    "llp": "LLP",
    "partnership": "Partnership",
}
G_FE2DB = {"Filed": "filed", "Due": "pending", "Overdue": "overdue"}
G_DB2FE = {
    "filed": "Filed",
    "pending": "Due",
    "overdue": "Overdue",
    "exempt": "Filed",
    None: "Pending",
}
A_FE2DB = {
    "Passed": "completed",
    "In Progress": "in_progress",
    "Pending": "pending",
    "Flagged": "flagged",
}
A_DB2FE = {
    "completed": "Passed",
    "in_progress": "In Progress",
    "pending": "Pending",
    "flagged": "Flagged",
    None: "Pending",
}


def _initials(name: str) -> str:
    words = name.strip().split()
    return "".join(w[0].upper() for w in words if w and w[0].isalpha())[:2] or "??"


def _rel_time(dt: datetime) -> str:
    if not dt:
        return "Recently"
    if not dt.tzinfo:
        dt = dt.replace(tzinfo=timezone.utc)
    s = int((datetime.now(timezone.utc) - dt).total_seconds())
    if s < 60:
        return "Just now"
    if s < 3600:
        return f"{s//60} min ago"
    if s < 86400:
        return f"{s//3600} hour{'s' if s//3600!=1 else ''} ago"
    if s < 172800:
        return "Yesterday"
    d = s // 86400
    if d < 30:
        return f"{d} days ago"
    return dt.strftime("%d %b %Y")


def _next_code(repo: ClientRepository) -> str:
    return f"C-{repo.get_max_code_sequence() + 1}"


class ClientService:

    def __init__(self, db: Session):
        self.repo = ClientRepository(db)

    # ── CREATE ─────────────────────────────────────────────────
    def create_client(self, data: ClientCreate, user_id: Optional[object] = None) -> ClientCardResponse:
        # Duplicate checks scoped to this user
        ex = self.repo.get_by_company_name(data.company, user_id=user_id)
        if ex and ex.status != "deleted":
            raise ConflictException(
                detail=f"'{data.company}' already exists ({ex.client_code})"
            )
        if data.gstin:
            dup = self.repo.get_by_gst(data.gstin, user_id=user_id)
            if dup and dup.status != "deleted":
                raise ConflictException(
                    detail=f"GSTIN {data.gstin} belongs to {dup.company_name}"
                )
        if data.pan:
            dup = self.repo.get_by_pan(data.pan, user_id=user_id)
            if dup and dup.status != "deleted":
                raise ConflictException(
                    detail=f"PAN {data.pan} belongs to {dup.company_name}"
                )

        client = Client(
            user_id=user_id,
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
            # new fields
            billing_cycle=data.clientType.lower() if data.clientType else "monthly",
            contact_number=data.contactNumber,
            email_address=data.emailAddress,
            location=data.location,
        )
        client = self.repo.create(client)

        # Seed initial GST record
        self.repo.db.add(
            GSTRecord(
                client_id=client.id,
                gst_period=date.today().strftime("%Y-%m"),
                gst_type="GSTR-3B",
                taxable_amount=Decimal(str(data.revenue)),
                cgst=Decimal("0"),
                sgst=Decimal("0"),
                igst=Decimal("0"),
                total_tax=Decimal("0"),
                filing_status=G_FE2DB.get(data.gst, "pending"),
                due_date=date.today() + timedelta(days=20),
            )
        )
        # Seed initial Tax record — status always "pending" until GST module updates it
        self.repo.db.add(
            TaxRecord(
                client_id=client.id,
                financial_year="2025-26",
                tax_type="income_tax",
                taxable_income=Decimal(str(data.revenue)),
                tds=Decimal("0"),
                advance_tax=Decimal("0"),
                total_tax=Decimal("0"),
                status="pending",
            )
        )
        # Seed initial Audit report — status always "pending" until Auditing module updates it
        self.repo.db.add(
            AuditReport(
                client_id=client.id,
                audit_type="statutory",
                audit_status="pending",
                findings="Initial audit record — client onboarded.",
                recommendations="Complete KYC and submit first year documents.",
            )
        )
        self.repo.db.commit()

        logger.info("Created client %s — %s for user %s", client.client_code, client.company_name, user_id)
        return self._card(
            client,
            G_FE2DB.get(data.gst, "pending"),
            "pending",  # tax — always Pending on creation; GST module updates later
            "pending",
        )  # audit — always Pending on creation; Auditing module updates later

    # ── LIST ───────────────────────────────────────────────────
    def get_clients(
        self,
        page=1,
        page_size=50,
        search=None,
        sort_by="created_at",
        sort_order="desc",
        status=None,
        risk_level=None,
        user_id: Optional[object] = None,
    ) -> PaginatedResponse:
        db_status = S_FE2DB.get(status, status.lower() if status else None)
        db_risk = R_FE2DB.get(risk_level, risk_level.lower() if risk_level else None)
        if db_status == "deleted":
            db_status = None

        clients, total = self.repo.get_all(
            page=page,
            page_size=page_size,
            search=search,
            sort_by=sort_by,
            sort_order=sort_order,
            status_filter=db_status,
            risk_filter=db_risk,
            user_id=user_id,
        )
        cards = [
            self._card(
                c,
                self.repo.get_latest_gst_status(c.id),
                self.repo.get_latest_tax_status(c.id),
                self.repo.get_latest_audit_status(c.id),
            )
            for c in clients
        ]
        return PaginatedResponse(
            items=cards,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=math.ceil(total / page_size) if page_size else 0,
        )

    # ── DASHBOARD ──────────────────────────────────────────────
    def get_client_dashboard(self, client_id, user_id: Optional[object] = None) -> ClientDashboardResponse:
        client = self.repo.get_full_dashboard(client_id, user_id=user_id)
        if not client or client.status == "deleted":
            raise NotFoundException(detail=f"Client {client_id} not found")
        return ClientDashboardResponse(
            client=ClientResponse.model_validate(client),
            gst=[GSTRecordResponse.model_validate(r) for r in client.gst_records],
            tax=[TaxRecordResponse.model_validate(r) for r in client.tax_records],
            audit=[AuditReportResponse.model_validate(r) for r in client.audit_reports],
            invoices=[InvoiceResponse.model_validate(r) for r in client.invoices],
            documents=[DocumentResponse.model_validate(r) for r in client.documents],
            accounting=[
                AccountingRecordResponse.model_validate(r)
                for r in client.accounting_records
            ],
        )

    # ── OVERVIEW ───────────────────────────────────────────────
    def get_client_overview(self, client_id, user_id: Optional[object] = None) -> ClientOverviewResponse:
        client = self._get_or_404(client_id, user_id=user_id)
        return ClientOverviewResponse(
            client_id=str(client.id),
            company_name=client.company_name,
            risk_level=R_DB2FE.get(client.risk_level, "Low"),
            compliance_status=self._compliance(
                self.repo.get_latest_gst_status(client.id),
                self.repo.get_latest_tax_status(client.id),
                self.repo.get_latest_audit_status(client.id),
            ),
            gst_status=G_DB2FE.get(
                self.repo.get_latest_gst_status(client.id), "Pending"
            ),
            tax_status=G_DB2FE.get(
                self.repo.get_latest_tax_status(client.id), "Pending"
            ),
            audit_status=A_DB2FE.get(
                self.repo.get_latest_audit_status(client.id), "Pending"
            ),
        )

    # ── UPDATE ─────────────────────────────────────────────────
    def update_client(self, client_id, data: ClientUpdate, user_id: Optional[object] = None) -> ClientCardResponse:
        client = self._get_or_404(client_id, user_id=user_id)
        patch = {}
        if data.company is not None:
            ex = self.repo.get_by_company_name(data.company, user_id=user_id)
            if ex and str(ex.id) != str(client_id) and ex.status != "deleted":
                raise ConflictException(detail=f"'{data.company}' already exists")
            patch["company_name"] = data.company.strip()
        if data.name is not None:
            patch["contact_person"] = data.name.strip()
        if data.type is not None:
            patch["client_type"] = T_FE2DB.get(data.type, data.type.lower())
        if data.status is not None:
            patch["status"] = S_FE2DB.get(data.status, data.status.lower())
        if data.risk is not None:
            patch["risk_level"] = R_FE2DB.get(data.risk, data.risk.lower())
        if data.gstin is not None:
            patch["gst_number"] = data.gstin
        if data.pan is not None:
            patch["pan_number"] = data.pan
        if data.email is not None:
            patch["email"] = data.email
        if data.phone is not None:
            patch["phone"] = data.phone
        if data.address is not None:
            patch["address"] = data.address
        if data.city is not None:
            patch["city"] = data.city
        if data.state is not None:
            patch["state"] = data.state
        if data.country is not None:
            patch["country"] = data.country
        # new fields
        if data.clientType is not None:
            patch["billing_cycle"] = data.clientType.lower()
        if data.contactNumber is not None:
            patch["contact_number"] = data.contactNumber
        if data.emailAddress is not None:
            patch["email_address"] = data.emailAddress
        if data.location is not None:
            patch["location"] = data.location
        client = self.repo.update(client, patch)
        return self._card(
            client,
            self.repo.get_latest_gst_status(client.id),
            self.repo.get_latest_tax_status(client.id),
            self.repo.get_latest_audit_status(client.id),
        )

    # ── DELETE ─────────────────────────────────────────────────
    def delete_client(self, client_id, user_id: Optional[object] = None) -> dict:
        client = self._get_or_404(client_id, user_id=user_id)
        self.repo.soft_delete(client)
        return {"message": f"Client {client.client_code} deleted"}

    # ── SUB-SECTIONS ───────────────────────────────────────────
    def get_gst_records(self, cid, user_id: Optional[object] = None):
        self._get_or_404(cid, user_id=user_id)
        return [
            GSTRecordResponse.model_validate(r) for r in self.repo.get_gst_records(cid)
        ]

    def get_tax_records(self, cid, user_id: Optional[object] = None):
        self._get_or_404(cid, user_id=user_id)
        return [
            TaxRecordResponse.model_validate(r) for r in self.repo.get_tax_records(cid)
        ]

    def get_audit_reports(self, cid, user_id: Optional[object] = None):
        self._get_or_404(cid, user_id=user_id)
        return [
            AuditReportResponse.model_validate(r)
            for r in self.repo.get_audit_reports(cid)
        ]

    def get_invoices(self, cid, user_id: Optional[object] = None):
        self._get_or_404(cid, user_id=user_id)
        return [InvoiceResponse.model_validate(r) for r in self.repo.get_invoices(cid)]

    def get_documents(self, cid, user_id: Optional[object] = None):
        self._get_or_404(cid, user_id=user_id)
        return [
            DocumentResponse.model_validate(r) for r in self.repo.get_documents(cid)
        ]

    def get_history(self, cid, user_id: Optional[object] = None) -> ClientHistoryResponse:
        self._get_or_404(cid, user_id=user_id)
        items: List[ActivityItem] = []
        for r in self.repo.get_gst_records(cid):
            items.append(
                ActivityItem(
                    id=str(r.id),
                    type="gst",
                    title=f"GST {r.gst_type}",
                    description=f"Period {r.gst_period} — {r.filing_status}",
                    date=r.created_at,
                    status=r.filing_status,
                )
            )
        for r in self.repo.get_tax_records(cid):
            items.append(
                ActivityItem(
                    id=str(r.id),
                    type="tax",
                    title=f"Tax — {r.tax_type}",
                    description=f"FY {r.financial_year} — {r.status}",
                    date=r.created_at,
                    status=r.status,
                )
            )
        for r in self.repo.get_audit_reports(cid):
            items.append(
                ActivityItem(
                    id=str(r.id),
                    type="audit",
                    title=f"{r.audit_type.title()} Audit",
                    description=f"Status: {r.audit_status}",
                    date=r.created_at,
                    status=r.audit_status,
                )
            )
        for r in self.repo.get_invoices(cid):
            items.append(
                ActivityItem(
                    id=str(r.id),
                    type="invoice",
                    title=f"Invoice {r.invoice_number}",
                    description=f"{r.vendor_name} — ₹{r.amount:,.0f}",
                    date=r.created_at,
                    status=None,
                )
            )
        for r in self.repo.get_documents(cid):
            items.append(
                ActivityItem(
                    id=str(r.id),
                    type="document",
                    title=r.file_name,
                    description=f"Type: {r.file_type}",
                    date=r.uploaded_at,
                    status=None,
                )
            )
        items.sort(key=lambda x: x.date, reverse=True)
        return ClientHistoryResponse(client_id=str(cid), activities=items)

    # ── SEED STARTER CLIENTS FOR NEW USER ─────────────────────
    def seed_starter_clients_for_user(self, user_id: object, user_name: str = "") -> List[Client]:
        """Automatically create 5 diverse starter clients for a newly registered CA."""
        existing, total = self.repo.get_all(user_id=user_id, page_size=1)
        if total > 0:
            logger.info("User %s already has %d clients, skipping seed", user_id, total)
            return []

        starter_templates = [
            {
                "company": "Nexis Infotech Solutions",
                "name": "Kunal Verma",
                "type": "company",
                "cycle": "monthly",
                "phone": "+91 98201 44102",
                "email": "accounts@nexisinfotech.in",
                "location": "Mumbai, Maharashtra",
                "city": "Mumbai",
                "state": "Maharashtra",
                "gstin": "27AABCN8891P1Z3",
                "pan": "AABCN8891P",
                "status": "active",
                "risk": "low",
                "gst_status": "filed",
                "tax_status": "completed",
                "audit_status": "completed",
                "revenue": "3450000",
            },
            {
                "company": "Horizon Logistics & Freight",
                "name": "Pooja Sharma",
                "type": "llp",
                "cycle": "quarterly",
                "phone": "+91 98765 21098",
                "email": "finance@horizonlogistics.co",
                "location": "Surat, Gujarat",
                "city": "Surat",
                "state": "Gujarat",
                "gstin": "24AAJCH4412R1Z8",
                "pan": "AAJCH4412R",
                "status": "active",
                "risk": "medium",
                "gst_status": "pending",
                "tax_status": "pending",
                "audit_status": "in_progress",
                "revenue": "1820000",
            },
            {
                "company": "Vanguard Retail Ventures",
                "name": "Vikramaditya Roy",
                "type": "partnership",
                "cycle": "monthly",
                "phone": "+91 98310 99482",
                "email": "billing@vanguardretail.in",
                "location": "Kolkata, West Bengal",
                "city": "Kolkata",
                "state": "West Bengal",
                "gstin": "19AABFV6623Q1Z5",
                "pan": "AABFV6623Q",
                "status": "pending",
                "risk": "high",
                "gst_status": "overdue",
                "tax_status": "pending",
                "audit_status": "flagged",
                "revenue": "4200000",
            },
            {
                "company": "Apex Pharma Labs",
                "name": "Dr. Sanjeev Kapoor",
                "type": "company",
                "cycle": "monthly",
                "phone": "+91 99490 12345",
                "email": "tax@apexpharmalabs.com",
                "location": "Hyderabad, Telangana",
                "city": "Hyderabad",
                "state": "Telangana",
                "gstin": "36AABCA9914L1Z2",
                "pan": "AABCA9914L",
                "status": "active",
                "risk": "low",
                "gst_status": "filed",
                "tax_status": "completed",
                "audit_status": "pending",
                "revenue": "5100000",
            },
            {
                "company": "Heritage Craft Exports",
                "name": "Meenakshi Sundaram",
                "type": "individual",
                "cycle": "quarterly",
                "phone": "+91 94440 67890",
                "email": "info@heritagecraftexports.com",
                "location": "Chennai, Tamil Nadu",
                "city": "Chennai",
                "state": "Tamil Nadu",
                "gstin": "33AAUPM5521N1Z0",
                "pan": "AAUPM5521N",
                "status": "inactive",
                "risk": "low",
                "gst_status": "filed",
                "tax_status": "completed",
                "audit_status": "completed",
                "revenue": "850000",
            },
        ]

        created_clients = []
        for t in starter_templates:
            c = Client(
                user_id=user_id,
                client_code=_next_code(self.repo),
                company_name=t["company"],
                contact_person=t["name"],
                client_type=t["type"],
                billing_cycle=t["cycle"],
                contact_number=t["phone"],
                email_address=t["email"],
                email=t["email"],
                phone=t["phone"],
                location=t["location"],
                city=t["city"],
                state=t["state"],
                country="India",
                gst_number=t["gstin"],
                pan_number=t["pan"],
                status=t["status"],
                risk_level=t["risk"],
            )
            c = self.repo.create(c)
            # Add initial GST, Tax, and Audit records
            self.repo.db.add(
                GSTRecord(
                    client_id=c.id,
                    gst_period=date.today().strftime("%Y-%m"),
                    gst_type="GSTR-3B",
                    taxable_amount=Decimal(t["revenue"]),
                    cgst=Decimal("0"),
                    sgst=Decimal("0"),
                    igst=Decimal("0"),
                    total_tax=Decimal("0"),
                    filing_status=t["gst_status"],
                    due_date=date.today() + timedelta(days=20),
                )
            )
            self.repo.db.add(
                TaxRecord(
                    client_id=c.id,
                    financial_year="2025-26",
                    tax_type="income_tax",
                    taxable_income=Decimal(t["revenue"]),
                    tds=Decimal("0"),
                    advance_tax=Decimal("0"),
                    total_tax=Decimal("0"),
                    status=t["tax_status"],
                )
            )
            self.repo.db.add(
                AuditReport(
                    client_id=c.id,
                    audit_type="statutory",
                    audit_status=t["audit_status"],
                    findings=f"Initial audit check completed for {t['company']}.",
                    recommendations="Maintain books updated as per statutory schedule.",
                )
            )
            self.repo.db.commit()
            created_clients.append(c)

        logger.info("Seeded %d starter clients for user %s (%s)", len(created_clients), user_id, user_name)
        return created_clients

    # ── HELPERS ────────────────────────────────────────────────
    def _get_or_404(self, client_id, user_id: Optional[object] = None) -> Client:
        c = self.repo.get_by_id(client_id, user_id=user_id)
        if not c or c.status == "deleted":
            raise NotFoundException(detail=f"Client {client_id} not found")
        return c

    def _card(self, client: Client, gst_s, tax_s, audit_s) -> ClientCardResponse:
        # GST status uses G_DB2FE: "filed"→"Filed", "pending"→"Due", "overdue"→"Overdue"
        # Tax/Audit use A_DB2FE: "pending"→"Pending", "completed"→"Passed", etc.
        # This keeps the workspace card consistent with what future modules will update.
        TAX_DB2FE = {
            "filed": "Filed",
            "pending": "Pending",
            "overdue": "Overdue",
            "exempt": "Filed",
            None: "Pending",
        }
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
            tax=TAX_DB2FE.get(tax_s, "Pending"),
            risk=R_DB2FE.get(client.risk_level, "Low"),
            lastActivity=_rel_time(client.updated_at),
            avatar=_initials(client.company_name),
            db_id=str(client.id),
        )

    @staticmethod
    def _compliance(gst, tax, audit) -> str:
        ss = [gst, tax, audit]
        if any(s == "overdue" for s in ss):
            return "non_compliant"
        if any(s in ("pending", "in_progress") for s in ss):
            return "partially_compliant"
        return "compliant"
