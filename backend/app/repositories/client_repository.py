"""
Client Repository — data access layer for the new UUID schema.
All 10 tables are UUID-keyed. Only client CRUD is needed for the
workspace module; additional tables are read via relationships.
"""

import logging
from typing import Optional, List, Tuple
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, desc, asc, func

from app.models.client import Client
from app.models.accounting_record import AccountingRecord
from app.models.gst_record import GSTRecord
from app.models.tax_record import TaxRecord
from app.models.audit_report import AuditReport
from app.models.invoice import Invoice
from app.models.document import Document

logger = logging.getLogger(__name__)

SORTABLE = {
    "created_at": Client.created_at,
    "updated_at": Client.updated_at,
    "company_name": Client.company_name,
    "client_code": Client.client_code,
    "status": Client.status,
    "risk_level": Client.risk_level,
}


class ClientRepository:

    def __init__(self, db: Session):
        self.db = db

    # ── List ───────────────────────────────────────────────────
    def get_all(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        status_filter: Optional[str] = None,
        risk_filter: Optional[str] = None,
    ) -> Tuple[List[Client], int]:
        q = self.db.query(Client).filter(Client.status != "deleted")

        if search:
            t = f"%{search.strip()}%"
            q = q.filter(
                or_(
                    Client.company_name.ilike(t),
                    Client.client_code.ilike(t),
                    Client.contact_person.ilike(t),
                    Client.gst_number.ilike(t),
                    Client.pan_number.ilike(t),
                    Client.email.ilike(t),
                )
            )
        if status_filter:
            q = q.filter(Client.status == status_filter.lower())
        if risk_filter:
            q = q.filter(Client.risk_level == risk_filter.lower())

        total = q.count()
        col = SORTABLE.get(sort_by, Client.created_at)
        q = q.order_by(asc(col) if sort_order == "asc" else desc(col))
        clients = q.offset((page - 1) * page_size).limit(page_size).all()
        return clients, total

    # ── Single ─────────────────────────────────────────────────
    def get_by_id(self, client_id) -> Optional[Client]:
        return self.db.query(Client).filter(Client.id == client_id).first()

    def get_by_code(self, code: str) -> Optional[Client]:
        return self.db.query(Client).filter(Client.client_code == code).first()

    def get_by_company_name(self, name: str) -> Optional[Client]:
        return (
            self.db.query(Client)
            .filter(func.lower(Client.company_name) == name.strip().lower())
            .first()
        )

    def get_by_gst(self, gst: str) -> Optional[Client]:
        return self.db.query(Client).filter(Client.gst_number == gst.upper()).first()

    def get_by_pan(self, pan: str) -> Optional[Client]:
        return self.db.query(Client).filter(Client.pan_number == pan.upper()).first()

    def get_full_dashboard(self, client_id) -> Optional[Client]:
        return (
            self.db.query(Client)
            .options(
                joinedload(Client.accounting_records),
                joinedload(Client.gst_records),
                joinedload(Client.tax_records),
                joinedload(Client.audit_reports),
                joinedload(Client.invoices),
                joinedload(Client.documents),
            )
            .filter(Client.id == client_id)
            .first()
        )

    def get_max_code_sequence(self) -> int:
        codes = self.db.query(Client.client_code).all()
        mx = 1041
        for (code,) in codes:
            try:
                n = int(code.split("-")[-1])
                mx = max(mx, n)
            except (ValueError, IndexError):
                pass
        return mx

    # ── Write ──────────────────────────────────────────────────
    def create(self, client: Client) -> Client:
        self.db.add(client)
        self.db.commit()
        self.db.refresh(client)
        logger.info("Created client %s — %s", client.client_code, client.company_name)
        return client

    def update(self, client: Client, patch: dict) -> Client:
        for k, v in patch.items():
            if hasattr(client, k) and v is not None:
                setattr(client, k, v)
        self.db.commit()
        self.db.refresh(client)
        return client

    def soft_delete(self, client: Client) -> Client:
        client.status = "deleted"
        self.db.commit()
        self.db.refresh(client)
        return client

    # ── Sub-records ────────────────────────────────────────────
    def get_gst_records(self, client_id) -> List[GSTRecord]:
        return self.db.query(GSTRecord).filter(GSTRecord.client_id == client_id).all()

    def get_tax_records(self, client_id) -> List[TaxRecord]:
        return self.db.query(TaxRecord).filter(TaxRecord.client_id == client_id).all()

    def get_audit_reports(self, client_id) -> List[AuditReport]:
        return (
            self.db.query(AuditReport).filter(AuditReport.client_id == client_id).all()
        )

    def get_invoices(self, client_id) -> List[Invoice]:
        return self.db.query(Invoice).filter(Invoice.client_id == client_id).all()

    def get_documents(self, client_id) -> List[Document]:
        return self.db.query(Document).filter(Document.client_id == client_id).all()

    # Latest status helpers for card view
    def get_latest_gst_status(self, client_id) -> Optional[str]:
        r = (
            self.db.query(GSTRecord.filing_status)
            .filter(GSTRecord.client_id == client_id)
            .order_by(desc(GSTRecord.created_at))
            .first()
        )
        return r[0] if r else None

    def get_latest_tax_status(self, client_id) -> Optional[str]:
        r = (
            self.db.query(TaxRecord.status)
            .filter(TaxRecord.client_id == client_id)
            .order_by(desc(TaxRecord.created_at))
            .first()
        )
        return r[0] if r else None

    def get_latest_audit_status(self, client_id) -> Optional[str]:
        r = (
            self.db.query(AuditReport.audit_status)
            .filter(AuditReport.client_id == client_id)
            .order_by(desc(AuditReport.created_at))
            .first()
        )
        return r[0] if r else None
