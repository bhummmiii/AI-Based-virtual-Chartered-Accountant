"""
AI Context Service — Structured Context Builder for FinLedger AI
================================================================
Assembles verified, backend-sourced context for the LLM layer.

SAFETY RULES (non-negotiable):
  1. Every query is scoped by client_id (UUID).
  2. Missing data is returned as None, NOT as zero.
  3. No accounting calculations are performed here — we delegate to
     the existing authoritative services (GstReconciliationService,
     TrialBalanceService, JournalEntryService, VoucherService).
  4. This service is READ-ONLY; it never writes to any table.
"""

import uuid
import logging
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func, and_

from app.models.client import Client
from app.models.user import User
from app.models.uploaded_document import UploadedDocument
from app.models.journal_entry import JournalEntry
from app.core.exceptions import NotFoundException, ForbiddenException

logger = logging.getLogger(__name__)


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fmt(v: Optional[Decimal]) -> Optional[str]:
    """Format Decimal as ₹-string, or None if unavailable."""
    if v is None:
        return None
    return f"₹{v:,.2f}"


def _safe_float(v) -> Optional[float]:
    """Convert to float; return None on any failure."""
    try:
        if v is None:
            return None
        return float(v)
    except Exception:
        return None


def _verify_client_access(db: Session, client_id: uuid.UUID, user: User) -> Client:
    """Raise 404/403 if client does not exist or user lacks access."""
    client = db.query(Client).filter(Client.id == client_id).first()
    if not client:
        raise NotFoundException(detail=f"Client {client_id} not found")
    if user.role != "admin" and client.user_id is not None and client.user_id != user.id:
        raise ForbiddenException(detail="Access denied to this client's data")
    return client


# ── Document Summary ────────────────────────────────────────────────────────────

def _get_document_summary(db: Session, client_id: uuid.UUID) -> Dict[str, Any]:
    """
    Return counts of uploaded documents by verification status.
    Scoped strictly to client_id.
    """
    from app.models.uploaded_document import UploadedDocument

    base = db.query(UploadedDocument).filter(UploadedDocument.client_id == client_id)

    total = base.count()
    verified = base.filter(UploadedDocument.status == "verified").count()
    unverified = base.filter(UploadedDocument.status != "verified").count()
    pending_ocr = base.filter(UploadedDocument.ocr_status == "pending").count()

    return {
        "total": total,
        "verified": verified,
        "unverified": unverified,
        "pending_ocr": pending_ocr,
    }


# ── Journal / Posting Summary ──────────────────────────────────────────────────

def _get_journal_summary(db: Session, client_id: uuid.UUID,
                          from_date: Optional[date] = None,
                          to_date: Optional[date] = None) -> Dict[str, Any]:
    """
    Count posted vs draft journal entries for the client+period.
    Scoped strictly to client_id.
    """
    base = db.query(JournalEntry).filter(JournalEntry.client_id == client_id)

    if from_date:
        base = base.filter(JournalEntry.entry_date >= from_date)
    if to_date:
        base = base.filter(JournalEntry.entry_date <= to_date)

    total = base.count()
    posted = base.filter(JournalEntry.status == "posted",
                          JournalEntry.is_reversed == False).count()   # noqa: E712
    draft = base.filter(JournalEntry.status == "draft").count()
    reversed_count = base.filter(JournalEntry.is_reversed == True).count()    # noqa: E712

    return {
        "total": total,
        "posted": posted,
        "draft": draft,
        "reversed": reversed_count,
    }


# ── GST Summary (delegates to authoritative GST service) ──────────────────────

def _get_gst_summary(db: Session, client_id: uuid.UUID, user: User,
                      period: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve GST figures from GstReconciliationService.generate_gstr3b.
    Returns None (not zero) if data is unavailable.
    Scoped to client_id + period.
    """
    try:
        from app.services.gst_reconciliation_service import GstReconciliationService
        result = GstReconciliationService.generate_gstr3b(
            db=db,
            client_id=client_id,
            user=user,
            period=period,
        )
        if result is None:
            return None

        # Extract from result — use None where data is missing, never default to 0
        def _d(key):
            val = getattr(result, key, None)
            if val is None:
                return None
            try:
                return float(val)
            except Exception:
                return None

        # Outward section
        outward = getattr(result, "outward_supplies", None)
        inward = getattr(result, "inward_itc", None)
        tax_liability = getattr(result, "tax_liability", None)
        net_payable = getattr(result, "net_tax_payable", None)

        def _from_section(section, attr):
            if section is None:
                return None
            val = getattr(section, attr, None)
            return _safe_float(val)

        return {
            "source": "gstr3b_service",
            "period": period,
            "outward_taxable": _from_section(outward, "total_taxable_value"),
            "cgst_outward": _from_section(outward, "total_cgst"),
            "sgst_outward": _from_section(outward, "total_sgst"),
            "igst_outward": _from_section(outward, "total_igst"),
            "itc_cgst": _from_section(inward, "eligible_cgst"),
            "itc_sgst": _from_section(inward, "eligible_sgst"),
            "itc_igst": _from_section(inward, "eligible_igst"),
            "net_tax_payable": _safe_float(net_payable) if net_payable is not None else None,
            "data_available": True,
        }
    except Exception as exc:
        logger.warning("[AIContextService] GST summary unavailable: %s", exc)
        return {"data_available": False, "reason": str(exc)}


# ── Discrepancy Summary (delegates to authoritative GST service) ───────────────

def _get_discrepancy_summary(db: Session, client_id: uuid.UUID, user: User,
                               period: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve discrepancy detection results from the existing engine.
    Scoped to client_id + period.
    """
    try:
        from app.services.gst_reconciliation_service import GstReconciliationService
        result = GstReconciliationService.detect_discrepancies(
            db=db,
            client_id=client_id,
            user=user,
            period=period,
        )
        if result is None:
            return None

        discrepancies = getattr(result, "discrepancies", None) or []
        return {
            "source": "discrepancy_detection_service",
            "total_discrepancies": len(discrepancies),
            "items": [
                {
                    "type": getattr(d, "discrepancy_type", None),
                    "severity": getattr(d, "severity", None),
                    "description": getattr(d, "description", None),
                    "invoice_id": str(getattr(d, "invoice_id", None) or ""),
                    "amount": _safe_float(getattr(d, "amount_difference", None)),
                }
                for d in discrepancies[:10]  # cap for context size
            ],
            "data_available": True,
        }
    except Exception as exc:
        logger.warning("[AIContextService] Discrepancy summary unavailable: %s", exc)
        return {"data_available": False, "reason": str(exc)}


# ── Financial Insights (delegates to authoritative GST service) ───────────────

def _get_financial_insights(db: Session, client_id: uuid.UUID, user: User,
                              period: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Retrieve CA-generated compliance score and observations.
    Scoped to client_id + period.
    """
    try:
        from app.services.gst_reconciliation_service import GstReconciliationService
        result = GstReconciliationService.get_financial_insights(
            db=db,
            client_id=client_id,
            user=user,
            period=period,
        )
        if result is None:
            return None

        observations = getattr(result, "ca_observations", None) or []
        checklist = getattr(result, "filing_checklist", None) or []
        score = getattr(result, "compliance_score", None)

        return {
            "source": "financial_insights_service",
            "compliance_score": _safe_float(score),
            "ca_observations": [
                {
                    "category": getattr(o, "category", None),
                    "severity": getattr(o, "severity", None),
                    "observation": getattr(o, "observation", None),
                    "recommendation": getattr(o, "recommendation", None),
                    "impact_amount": _safe_float(getattr(o, "impact_amount", None)),
                }
                for o in observations[:15]
            ],
            "checklist_pending": sum(
                1 for c in checklist if not getattr(c, "completed", True)
            ),
            "checklist_total": len(checklist),
            "data_available": True,
        }
    except Exception as exc:
        logger.warning("[AIContextService] Financial insights unavailable: %s", exc)
        return {"data_available": False, "reason": str(exc)}


# ── Public API ────────────────────────────────────────────────────────────────

def build_client_context(
    db: Session,
    client_id: uuid.UUID,
    user: User,
    period: Optional[str] = None,
    include_gst: bool = True,
    include_discrepancies: bool = True,
    include_insights: bool = True,
) -> Dict[str, Any]:
    """
    Build a structured, evidence-based context block for the LLM.

    All figures come from the authoritative backend services.
    Missing data is represented as None — never as zero.
    Scoped strictly to client_id (UUID).
    """
    client = _verify_client_access(db, client_id, user)

    context: Dict[str, Any] = {
        "client": {
            "client_id": str(client.id),
            "name": client.company_name,
            "gstin": client.gst_number or None,
            "pan": client.pan_number or None,
            "type": client.client_type,
            "risk_level": client.risk_level,
            "status": client.status,
        },
        "period": period or "not specified",
        "source": "verified_backend",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    # Documents
    context["documents"] = _get_document_summary(db, client_id)

    # Journals
    context["journals"] = _get_journal_summary(db, client_id)

    # GST
    if include_gst:
        context["gst"] = _get_gst_summary(db, client_id, user, period)
    else:
        context["gst"] = None

    # Discrepancies
    if include_discrepancies:
        context["discrepancies"] = _get_discrepancy_summary(db, client_id, user, period)
    else:
        context["discrepancies"] = None

    # Financial insights
    if include_insights:
        context["financial_insights"] = _get_financial_insights(db, client_id, user, period)
    else:
        context["financial_insights"] = None

    return context


def build_context_prompt_fragment(context: Dict[str, Any]) -> str:
    """
    Convert a structured context dict into a concise, LLM-readable text block.
    Only includes fields that have actual values — never fabricates missing data.
    """
    lines = []

    client = context.get("client", {})
    lines.append(f"CLIENT: {client.get('name', 'Unknown')} | GSTIN: {client.get('gstin') or 'Not available'} | "
                 f"Type: {client.get('type', 'Unknown')} | Risk: {client.get('risk_level', 'Unknown')}")

    period = context.get("period")
    if period and period != "not specified":
        lines.append(f"PERIOD: {period}")

    # Documents
    docs = context.get("documents") or {}
    if docs.get("total", 0) > 0:
        lines.append(
            f"DOCUMENTS: {docs['total']} total | "
            f"{docs.get('verified', 0)} verified | "
            f"{docs.get('unverified', 0)} unverified | "
            f"{docs.get('pending_ocr', 0)} pending OCR"
        )

    # Journals
    journals = context.get("journals") or {}
    if journals.get("total", 0) > 0:
        lines.append(
            f"JOURNAL ENTRIES: {journals['total']} total | "
            f"{journals.get('posted', 0)} posted | "
            f"{journals.get('draft', 0)} draft | "
            f"{journals.get('reversed', 0)} reversed"
        )

    # GST
    gst = context.get("gst")
    if gst:
        if not gst.get("data_available", True):
            lines.append(f"GST DATA: Unavailable — {gst.get('reason', 'service error')}")
        else:
            gst_parts = []
            if gst.get("outward_taxable") is not None:
                gst_parts.append(f"Outward taxable: ₹{gst['outward_taxable']:,.2f}")
            if gst.get("cgst_outward") is not None:
                gst_parts.append(f"CGST: ₹{gst['cgst_outward']:,.2f}")
            if gst.get("sgst_outward") is not None:
                gst_parts.append(f"SGST: ₹{gst['sgst_outward']:,.2f}")
            if gst.get("igst_outward") is not None:
                gst_parts.append(f"IGST: ₹{gst['igst_outward']:,.2f}")
            if gst.get("itc_igst") is not None or gst.get("itc_cgst") is not None:
                itc_total = sum(filter(None, [gst.get("itc_cgst"), gst.get("itc_sgst"), gst.get("itc_igst")]))
                gst_parts.append(f"ITC: ₹{itc_total:,.2f}")
            if gst.get("net_tax_payable") is not None:
                gst_parts.append(f"Net payable: ₹{gst['net_tax_payable']:,.2f}")
            if gst_parts:
                lines.append("GST (source: posted GST ledger): " + " | ".join(gst_parts))
            else:
                lines.append("GST DATA: No posted GST entries found for the period")

    # Discrepancies
    disc = context.get("discrepancies")
    if disc:
        if not disc.get("data_available", True):
            lines.append(f"DISCREPANCIES: Service unavailable — {disc.get('reason', 'error')}")
        elif disc.get("total_discrepancies", 0) > 0:
            lines.append(f"DISCREPANCIES: {disc['total_discrepancies']} found")
            for item in (disc.get("items") or [])[:5]:
                sev = item.get("severity", "")
                desc = item.get("description", "")
                amt = item.get("amount")
                amt_str = f" (₹{amt:,.2f})" if amt else ""
                lines.append(f"  [{sev.upper()}] {desc}{amt_str}")
        else:
            lines.append("DISCREPANCIES: None detected")

    # Financial insights
    fi = context.get("financial_insights")
    if fi:
        if not fi.get("data_available", True):
            lines.append(f"INSIGHTS: Service unavailable — {fi.get('reason', 'error')}")
        else:
            score = fi.get("compliance_score")
            if score is not None:
                lines.append(f"COMPLIANCE SCORE: {score:.0f}/100")
            pending = fi.get("checklist_pending", 0)
            total_cl = fi.get("checklist_total", 0)
            if total_cl > 0:
                lines.append(f"FILING CHECKLIST: {pending} pending of {total_cl} items")
            for obs in (fi.get("ca_observations") or [])[:5]:
                sev = obs.get("severity", "")
                observation = obs.get("observation", "")
                rec = obs.get("recommendation", "")
                if observation:
                    lines.append(f"  [{sev.upper()}] {observation}")
                if rec:
                    lines.append(f"    → Recommendation: {rec}")

    lines.append("SOURCE: All figures are derived from the FinLedger verified backend. "
                 "Data shown as 'not available' means no verified records exist for this client/period.")

    return "\n".join(lines)


# ── Client Name → UUID resolution ─────────────────────────────────────────────

def resolve_client_by_name(db: Session, user: User, name_query: str) -> List[Dict[str, Any]]:
    """
    Resolve a partial client name or GSTIN to a list of matching clients
    accessible by the current user.

    Returns a list (may have 0, 1, or multiple matches).
    The caller must handle ambiguity by asking the user for clarification.
    """
    name_q = f"%{name_query.strip()}%"

    query = db.query(Client).filter(
        Client.company_name.ilike(name_q)
    )

    # If not admin, restrict to own clients
    if user.role != "admin":
        query = query.filter(Client.user_id == user.id)

    matches = query.limit(10).all()

    return [
        {
            "client_id": str(c.id),
            "name": c.company_name,
            "gstin": c.gst_number,
            "client_code": c.client_code,
        }
        for c in matches
    ]


def resolve_client_by_gstin(db: Session, user: User, gstin: str) -> Optional[Dict[str, Any]]:
    """
    Resolve a GSTIN to a client.
    Returns None if not found or not accessible.
    """
    query = db.query(Client).filter(
        Client.gst_number == gstin.strip().upper()
    )
    if user.role != "admin":
        query = query.filter(Client.user_id == user.id)

    client = query.first()
    if not client:
        return None
    return {
        "client_id": str(client.id),
        "name": client.company_name,
        "gstin": client.gst_number,
        "client_code": client.client_code,
    }
