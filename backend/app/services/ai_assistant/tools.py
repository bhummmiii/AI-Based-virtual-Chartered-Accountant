"""
Verified tools for the AI assistant.

Every tool:
  * is READ-ONLY,
  * is scoped to ONE client (or, for workspace tools, to the caller's own clients),
  * delegates to the existing authoritative services wherever one exists
    (GST reconciliation, trial balance, financial statements),
  * returns a `Fact` with explicit availability + source — missing data is reported
    as missing, never as zero and never invented.
"""

from __future__ import annotations

import calendar
import logging
from collections import Counter, defaultdict
from datetime import date, datetime
from decimal import Decimal
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func

from app.core.config import get_settings
from app.models.accounting_record import AccountingRecord
from app.models.audit_report import AuditReport
from app.models.client import Client
from app.models.gst_record import GSTRecord
from app.models.journal_entry import JournalEntry
from app.models.tax_record import TaxRecord
from app.models.uploaded_document import UploadedDocument
from app.services.ai_assistant.facts import (
    Fact, ToolContext, client_link, fmt_date, inr, to_decimal,
)
from app.services.ai_assistant.resolver import name_tokens, tokenize

logger = logging.getLogger(__name__)

ZERO = Decimal("0.00")

_CATEGORY_LABELS = {
    "sales_records": "Sales records", "purchase_records": "Purchase records",
    "credit_note": "Credit notes", "debit_note": "Debit notes", "b2b_invoice": "B2B invoices",
    "b2c_invoice": "B2C invoices", "hsn_sac": "HSN/SAC", "e_invoice": "E-invoices",
    "e_way_bill": "E-way bills", "gst_challan": "GST challans", "gst_return": "GST returns",
    "gst_notice": "GST notices", "document_list": "Document list (KYC)",
}


def _cat(c: Optional[str]) -> str:
    return _CATEGORY_LABELS.get((c or "").lower(), (c or "uncategorised").replace("_", " ").title())


def _src(client: Client, tab: str) -> Tuple[str, Optional[str], str, str]:
    return str(client.id), client_link(client.client_code, tab), client.client_code, client.company_name


def _base(client: Client, key: str, title: str, source: str, tab: str) -> Fact:
    cid, link, code, name = _src(client, tab)
    return Fact(key=key, title=title, source=source, client_id=cid, client_code=code,
                client_name=name, link=link)


def _unavailable(client: Client, key: str, title: str, source: str, tab: str, reason: str) -> Fact:
    f = _base(client, key, title, source, tab)
    f.available = False
    f.note = reason
    f.lines = [reason]
    return f


def _period_args(ctx: ToolContext) -> dict:
    if ctx.period.is_set:
        return {"from_date": ctx.period.from_date, "to_date": ctx.period.to_date}
    return {"from_date": None, "to_date": None}


def safe_tool(key: str, title: str, source: str, tab: str):
    """Decorator: a failing tool yields an 'unavailable' Fact instead of an exception."""
    def deco(fn: Callable[..., Fact]):
        def wrapper(ctx: ToolContext, client: Client, *args, **kwargs) -> Fact:
            try:
                return fn(ctx, client, *args, **kwargs)
            except Exception as exc:  # noqa: BLE001 — deliberate: never break the whole answer
                logger.warning("[AI tool %s] failed for %s: %s", key, getattr(client, "client_code", "?"), exc)
                try:
                    ctx.db.rollback()
                except Exception:  # pragma: no cover
                    pass
                detail = getattr(exc, "detail", None) or str(exc) or exc.__class__.__name__
                return _unavailable(client, key, title, source, tab,
                                    f"{title} could not be computed right now ({str(detail)[:160]}).")
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


_DATE_FORMATS = ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d",
                 "%d-%b-%Y", "%d %b %Y", "%d-%b-%y", "%d/%m/%y", "%d %B %Y", "%b %d, %Y")


def parse_doc_date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    s = s.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _posted_je_count(ctx: ToolContext, client_id) -> int:
    q = ctx.db.query(func.count(JournalEntry.id)).filter(
        JournalEntry.client_id == client_id,
        JournalEntry.status == "posted",
        JournalEntry.is_reversed == False,  # noqa: E712
    )
    if ctx.period.is_set:
        q = q.filter(JournalEntry.entry_date >= ctx.period.from_date,
                     JournalEntry.entry_date <= ctx.period.to_date)
    return int(q.scalar() or 0)


# ══════════════════════════════════════════════════════════════════════════════
#  1. Client profile
# ══════════════════════════════════════════════════════════════════════════════

def tool_profile(ctx: ToolContext, client: Client) -> Fact:
    f = _base(client, "profile", "Client profile", "Client master record", "overview")
    ctype = (client.client_type or "company")
    ctype = "LLP" if ctype.lower() == "llp" else ctype.title()
    f.lines = [
        f"Client: {client.company_name} ({client.client_code})",
        f"Type: {ctype} · Status: {(client.status or 'unknown').title()} · "
        f"Risk level: {(client.risk_level or 'unknown').title()}",
        f"GSTIN: {client.gst_number or 'not on file'} · PAN: {client.pan_number or 'not on file'}",
        f"Return filing frequency: {client.return_frequency or client.billing_cycle or 'not set'}",
        f"Contact person: {client.contact_person or 'not on file'}"
        + (f" · Phone: {client.contact_number or client.phone}" if (client.contact_number or client.phone) else "")
        + (f" · Email: {client.email_address or client.email}" if (client.email_address or client.email) else ""),
        f"Location: {client.location or ', '.join(x for x in (client.city, client.state) if x) or 'not on file'}",
    ]
    f.compact = (f"{client.client_code} — {client.company_name} · {ctype} · "
                 f"{(client.risk_level or 'unknown').title()} risk · {(client.status or 'unknown').title()}")
    f.data = {"risk": client.risk_level, "status": client.status}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  2. Documents / invoices
# ══════════════════════════════════════════════════════════════════════════════

@safe_tool("documents", "Invoices & documents", "Uploaded documents register", "invoices")
def tool_documents(ctx: ToolContext, client: Client) -> Fact:
    cols = (UploadedDocument.id, UploadedDocument.document_category, UploadedDocument.status,
            UploadedDocument.ocr_status, UploadedDocument.invoice_number, UploadedDocument.invoice_date,
            UploadedDocument.vendor, UploadedDocument.customer, UploadedDocument.amount,
            UploadedDocument.uploaded_at)
    rows = (ctx.db.query(*cols).filter(UploadedDocument.client_id == client.id)
            .order_by(UploadedDocument.uploaded_at.desc()).limit(5000).all())

    undated = 0
    kept = []
    for r in rows:
        d = parse_doc_date(r.invoice_date)
        if ctx.period.is_set:
            if d is None:
                undated += 1
                continue
            if not (ctx.period.from_date <= d <= ctx.period.to_date):
                continue
        kept.append((r, d))

    f = _base(client, "documents", "Invoices & documents", "Uploaded documents register", "invoices")
    total = len(kept)
    if total == 0:
        f.available = False
        scope = f" in {ctx.period.display}" if ctx.period.is_set else ""
        f.note = f"No documents are recorded for {client.company_name}{scope}."
        f.lines = [f.note] + ([f"{undated} undated document(s) were excluded from the period filter."] if undated else [])
        f.compact = "no documents"
        f.data = {"total": 0, "unverified": 0}
        return f

    status = Counter((r.status or "unknown").lower() for r, _ in kept)
    verified = status.get("verified", 0)
    rejected = status.get("rejected", 0)
    unverified = total - verified - rejected
    ocr_pending = sum(1 for r, _ in kept if (r.ocr_status or "").lower() in ("pending", "processing"))
    ocr_failed = sum(1 for r, _ in kept if (r.ocr_status or "").lower() == "failed")

    by_cat: Dict[str, List] = defaultdict(list)
    for r, _ in kept:
        by_cat[r.document_category].append(r)

    lines = [f"Documents on record ({ctx.period.display}): {total}",
             "Status — " + " · ".join(f"{k.title()}: {v}" for k, v in sorted(status.items()))]
    lines.append(f"Awaiting verification: {unverified}" if unverified else "All non-rejected documents are verified.")
    if ocr_pending:
        lines.append(f"OCR still pending/processing: {ocr_pending}")
    if ocr_failed:
        lines.append(f"OCR failed: {ocr_failed}")
    for cat, items in sorted(by_cat.items(), key=lambda kv: -len(kv[1])):
        amt = sum((to_decimal(i.amount) or ZERO for i in items), ZERO)
        has_amt = any(i.amount is not None for i in items)
        lines.append(f"{_cat(cat)}: {len(items)}" + (f" (invoice value {inr(amt)})" if has_amt else ""))
    if undated:
        lines.append(f"{undated} undated document(s) excluded from this period filter.")

    def _recency(x):
        up = x[0].uploaded_at
        return (x[1] or date.min, up.timestamp() if up else 0.0)

    recent = sorted(kept, key=_recency, reverse=True)[:5]
    lines.append("Most recent documents:")
    for r, d in recent:
        party = r.vendor or r.customer or "party not captured"
        lines.append(f"- {r.invoice_number or 'no number'} · {_cat(r.document_category)} · {party} · "
                     f"{r.invoice_date or 'no date'} · {inr(r.amount) if r.amount is not None else 'amount not captured'} · "
                     f"{(r.status or 'unknown')}")

    # Party-specific lookup: does the message name a vendor/customer of THIS client?
    msg_tokens = set(tokenize(ctx.message))
    client_sig = set(name_tokens(client.company_name or ""))
    parties: Dict[str, List] = defaultdict(list)
    for r, _ in kept:
        for pname in {r.vendor, r.customer}:
            if not pname:
                continue
            sig = set(name_tokens(pname))
            if sig and sig != client_sig and sig <= msg_tokens and any(len(t) >= 3 for t in sig):
                parties[pname].append(r)
    for pname, items in list(parties.items())[:3]:
        amt = sum((to_decimal(i.amount) or ZERO for i in items), ZERO)
        lines.append(f"Documents involving {pname}: {len(items)} (total {inr(amt)})")
        for r in items[:8]:
            lines.append(f"- {r.invoice_number or 'no number'} · {_cat(r.document_category)} · "
                         f"{r.invoice_date or 'no date'} · {inr(r.amount) if r.amount is not None else 'amount not captured'} · {r.status}")

    f.lines = lines
    f.compact = f"{total} documents ({unverified} awaiting verification)"
    f.data = {"total": total, "verified": verified, "unverified": unverified, "rejected": rejected,
              "ocr_pending": ocr_pending}
    return f


@safe_tool("invoice_lookup", "Invoice lookup", "Uploaded documents register", "invoices")
def tool_invoice_lookup(ctx: ToolContext, client: Client, refs: List[str]) -> Fact:
    f = _base(client, "invoice_lookup", "Invoice lookup", "Uploaded documents register", "invoices")
    lines: List[str] = []
    found_any = False
    for ref in refs:
        q = ctx.db.query(UploadedDocument).filter(UploadedDocument.client_id == client.id)
        exact = q.filter(func.upper(UploadedDocument.invoice_number) == ref.upper()).all()
        docs = exact
        approx = False
        if not docs and len(ref) >= 3:
            docs = q.filter(UploadedDocument.invoice_number.ilike(f"%{ref}%")).limit(5).all()
            approx = bool(docs)
        if not docs:
            lines.append(f"No document with invoice number '{ref}' exists for {client.company_name}.")
            continue
        found_any = True
        if approx:
            lines.append(f"No exact match for '{ref}'; closest invoice number(s):")
        for d in docs[:5]:
            posted = ctx.db.query(JournalEntry.id).filter(
                JournalEntry.document_id == d.id, JournalEntry.status == "posted",
                JournalEntry.is_reversed == False,  # noqa: E712
            ).first() is not None
            party = d.vendor or d.customer or "party not captured"
            tax_bits = [f"{n} {inr(v)}" for n, v in (("CGST", d.cgst), ("SGST", d.sgst), ("IGST", d.igst)) if v]
            lines.append(
                f"Invoice {d.invoice_number} · {_cat(d.document_category)} · {party} · date {d.invoice_date or 'not captured'}")
            lines.append(
                f"  Taxable {inr(d.taxable_amount) if d.taxable_amount is not None else 'not captured'} · "
                f"Tax {', '.join(tax_bits) if tax_bits else 'none captured'} · "
                f"Total {inr(d.amount) if d.amount is not None else 'not captured'}")
            lines.append(
                f"  Status: {d.status} · OCR: {d.ocr_status or 'n/a'} · "
                f"Posted to ledger: {'yes' if posted else 'no'}"
                + (f" · GSTIN: {d.gstin}" if d.gstin else ""))
    f.lines = lines
    f.available = found_any
    f.note = None if found_any else lines[0] if lines else "No matching invoice."
    f.compact = lines[0] if lines else None
    f.data = {"found": found_any}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  3. GST (GSTR-3B) — delegates to GstReconciliationService
# ══════════════════════════════════════════════════════════════════════════════

@safe_tool("gst", "GST summary", "GSTR-3B computation (posted ledger entries)", "gst")
def tool_gst(ctx: ToolContext, client: Client) -> Fact:
    from app.services.gst_reconciliation_service import GstReconciliationService

    src = "GSTR-3B computation (posted ledger entries)"
    if _posted_je_count(ctx, client.id) == 0:
        scope = f" in {ctx.period.display}" if ctx.period.is_set else ""
        f = _unavailable(client, "gst", "GST summary", src, "gst",
                         f"No posted ledger entries exist for {client.company_name}{scope}, so GST liability "
                         f"cannot be computed. GST figures only come from invoices posted to the ledger.")
        f.compact = "no posted ledger entries — GST not computable"
        return f

    r = GstReconciliationService.generate_gstr3b(
        db=ctx.db, client_id=client.id, user=ctx.user, period=None, **_period_args(ctx))
    o, net, rev = r.table_3_1_outward, r.table_4_net_itc, r.table_4_itc_reversed
    out_total = o.cgst + o.sgst + o.igst + (o.cess or ZERO)
    itc_total = net.cgst + net.sgst + net.igst
    rev_total = rev.cgst + rev.sgst + rev.igst

    f = _base(client, "gst", "GST summary", src, "gst")
    lines = [
        f"Period: {ctx.period.display}",
        f"Outward taxable value: {inr(o.taxable_value)}",
        f"Output tax — CGST {inr(o.cgst)}, SGST {inr(o.sgst)}, IGST {inr(o.igst)} (total {inr(out_total)})",
        f"Net ITC available — CGST {inr(net.cgst)}, SGST {inr(net.sgst)}, IGST {inr(net.igst)} (total {inr(itc_total)})",
    ]
    if rev_total:
        lines.append(f"ITC reversed: {inr(rev_total)}")
    lines.append(f"Net GST payable in cash: {inr(r.tax_payable_in_cash)}")
    if r.excess_credit_carried_forward and r.excess_credit_carried_forward > 0:
        lines.append(f"Excess ITC carried forward: {inr(r.excess_credit_carried_forward)}")
    if r.negative_liability_carried_forward and r.negative_liability_carried_forward > 0:
        lines.append(f"Negative liability carried forward: {inr(r.negative_liability_carried_forward)}")
    if r.itc_reversal_payable_total and r.itc_reversal_payable_total > 0:
        lines.append(f"ITC reversal payable: {inr(r.itc_reversal_payable_total)}")
    if r.settlement_summary:
        lines.append(f"Settlement: {r.settlement_summary}")
    if r.needs_ca_review:
        lines.append("Flagged for CA review: " + ("; ".join(r.review_notes[:3]) if r.review_notes else "see GST tab"))
    if o.taxable_value == 0 and itc_total == 0 and r.tax_payable_in_cash == 0:
        lines.append("No GST-relevant posted entries were found for this period.")
    f.lines = lines
    f.compact = (f"output tax {inr(out_total)} · net ITC {inr(itc_total)} · "
                 f"cash payable {inr(r.tax_payable_in_cash)}")
    f.data = {"output_tax": out_total, "net_itc": itc_total, "cash_payable": r.tax_payable_in_cash,
              "excess_itc": r.excess_credit_carried_forward, "taxable": o.taxable_value}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  4. ITC (books vs ledger)
# ══════════════════════════════════════════════════════════════════════════════

@safe_tool("itc", "Input Tax Credit", "ITC reconciliation (purchase invoices vs ledger)", "gst")
def tool_itc(ctx: ToolContext, client: Client) -> Fact:
    from app.services.gst_reconciliation_service import GstReconciliationService

    src = "ITC reconciliation (purchase invoices vs ledger)"
    r = GstReconciliationService.reconcile_gstr2b(
        db=ctx.db, client_id=client.id, user=ctx.user, period=None, **_period_args(ctx))
    f = _base(client, "itc", "Input Tax Credit", src, "gst")

    ledger_total = r.ledger_total_input_tax
    lines = [
        f"Period: {ctx.period.display}",
        f"Inward taxable value (purchase documents): {inr(r.total_inward_taxable)}",
        f"Eligible ITC — CGST {inr(r.eligible_itc_cgst)}, SGST {inr(r.eligible_itc_sgst)}, "
        f"IGST {inr(r.eligible_itc_igst)} (total {inr(r.total_eligible_itc)})",
    ]
    if r.ineligible_itc and r.ineligible_itc > 0:
        lines.append(f"Ineligible / blocked ITC: {inr(r.ineligible_itc)}")
    lines.append(f"ITC booked in ledger (input tax accounts): {inr(ledger_total)}")
    lines.append(f"Variance (documents vs ledger): {inr(r.itc_variance)} — "
                 + ("reconciled" if r.is_reconciled else "NOT reconciled, review needed"))
    pending = [i for i in r.invoices if (i.reconciliation_status or "matched") != "matched"]
    lines.append(f"Purchase documents considered: {len(r.invoices)}; needing attention: {len(pending)}")
    for i in pending[:5]:
        lines.append(f"- {i.invoice_number or 'no number'} · {i.party_name or 'party not captured'} · "
                     f"tax {inr(i.total_tax)} · {i.reconciliation_status}")
    note = ("ITC is reconciled between purchase invoices recorded in FinLedger and your ledger. "
            "Government GSTR-2B portal data is not imported, so portal-level mismatches cannot be reported.")
    lines.append(f"Note: {note}")
    f.lines = lines
    f.note = note
    f.compact = (f"eligible ITC {inr(r.total_eligible_itc)} · ledger {inr(ledger_total)} · "
                 f"{'reconciled' if r.is_reconciled else 'variance ' + inr(r.itc_variance)}")
    f.data = {"eligible": r.total_eligible_itc, "ledger": ledger_total, "variance": r.itc_variance,
              "reconciled": r.is_reconciled, "pending": len(pending)}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  5. Discrepancies
# ══════════════════════════════════════════════════════════════════════════════

_SEV_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}


@safe_tool("discrepancies", "Discrepancies", "Discrepancy detection engine (GST rules)", "insights")
def tool_discrepancies(ctx: ToolContext, client: Client) -> Fact:
    from app.services.gst_reconciliation_service import GstReconciliationService

    src = "Discrepancy detection engine (GST rules)"
    doc_count = ctx.db.query(func.count(UploadedDocument.id)).filter(
        UploadedDocument.client_id == client.id).scalar() or 0
    je_count = ctx.db.query(func.count(JournalEntry.id)).filter(JournalEntry.client_id == client.id).scalar() or 0
    if doc_count == 0 and je_count == 0:
        f = _unavailable(client, "discrepancies", "Discrepancies", src, "insights",
                         f"{client.company_name} has no documents or ledger entries yet, so there is nothing to check.")
        f.compact = "no data to check"
        return f

    r = GstReconciliationService.detect_discrepancies(
        db=ctx.db, client_id=client.id, user=ctx.user, period=None, **_period_args(ctx))
    f = _base(client, "discrepancies", "Discrepancies", src, "insights")
    items = sorted(r.discrepancies, key=lambda d: (_SEV_ORDER.get((d.severity or "").upper(), 3),
                                                   -(to_decimal(d.variance_amount) or ZERO)))
    if r.total_discrepancies == 0:
        f.lines = [f"No discrepancies detected for {ctx.period.display}.",
                   "Checks run: missing GSTIN, tax-math mismatch, unposted invoices, duplicate invoices, "
                   "unlinked ledger entries, timing mismatch."]
        f.compact = "no discrepancies detected"
        f.data = {"total": 0, "high": 0}
        return f

    lines = [f"Discrepancies found: {r.total_discrepancies} (High {r.high_count}, Medium {r.medium_count}, "
             f"Low {r.low_count}); tax at risk {inr(r.total_tax_at_risk)}"]
    for d in items[:8]:
        bits = [f"[{(d.severity or '').upper()}] {d.title}: {d.description}"]
        if d.invoice_number:
            bits.append(f"invoice {d.invoice_number}")
        if d.party_name:
            bits.append(d.party_name)
        if d.variance_amount and to_decimal(d.variance_amount) != ZERO:
            bits.append(f"variance {inr(d.variance_amount)}")
        text = " · ".join(bits) + f" → {d.recommended_action}"
        if d.statutory_reference:
            text += f" ({d.statutory_reference})"
        lines.append(f"- {text}")
    if r.total_discrepancies > 8:
        lines.append(f"…and {r.total_discrepancies - 8} more (open the GST tab for the full list).")
    f.lines = lines
    f.compact = f"{r.total_discrepancies} discrepancies ({r.high_count} high); tax at risk {inr(r.total_tax_at_risk)}"
    f.data = {"total": r.total_discrepancies, "high": r.high_count, "medium": r.medium_count,
              "low": r.low_count, "tax_at_risk": r.total_tax_at_risk}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  6. Financial insights / compliance score
# ══════════════════════════════════════════════════════════════════════════════

@safe_tool("insights", "Compliance health", "Financial insights engine (CA review)", "insights")
def tool_insights(ctx: ToolContext, client: Client) -> Fact:
    from app.services.gst_reconciliation_service import GstReconciliationService

    src = "Financial insights engine (CA review)"
    doc_count = ctx.db.query(func.count(UploadedDocument.id)).filter(
        UploadedDocument.client_id == client.id).scalar() or 0
    if doc_count == 0 or _posted_je_count(ctx, client.id) == 0:
        f = _unavailable(client, "insights", "Compliance health", src, "insights",
                         f"A compliance score for {client.company_name} needs documents posted to the ledger; "
                         f"none are available yet" + (f" for {ctx.period.display}." if ctx.period.is_set else "."))
        f.compact = "compliance score not available (nothing posted)"
        return f

    r, period_note = _insights_for_range(ctx, client)
    f = _base(client, "insights", "Compliance health", src, "insights")
    lines = [f"Compliance score: {r.compliance_score}/100 · Risk: {r.risk_level}"]
    if period_note:
        lines.append(period_note)
    for o in r.ca_observations[:5]:
        lines.append(f"- {o}")
    for c in r.action_checklist:
        lines.append(f"- Check [{c.status}] {c.check_name}: {c.message}"
                     + (f" ({c.statutory_section})" if c.statutory_section else ""))
    f.lines = lines
    f.compact = f"compliance score {r.compliance_score}/100 ({r.risk_level} risk)"
    f.data = {"score": r.compliance_score, "risk": r.risk_level,
              "pending_checks": sum(1 for c in r.action_checklist if c.status != "PASSED")}
    return f


def _insights_for_range(ctx: ToolContext, client: Client):
    """
    get_financial_insights only accepts a period *label* (month or quarter). Map the parsed
    period onto one it understands; for any other range say so honestly instead of
    silently answering for a different window.
    """
    from app.services.gst_reconciliation_service import GstReconciliationService
    p = ctx.period
    label: Optional[str] = None
    note: Optional[str] = None
    if p.is_set:
        same_month = (p.from_date.year == p.to_date.year and p.from_date.month == p.to_date.month)
        qmap = {(4, 6): 1, (7, 9): 2, (10, 12): 3, (1, 3): 4}
        q = qmap.get((p.from_date.month, p.to_date.month))
        if same_month:
            label = f"{p.from_date.year}-{p.from_date.month:02d}"
        elif q and p.from_date.day == 1:
            label = f"Q{q} {p.from_date.year if q != 4 else p.from_date.year - 1}"
        else:
            note = (f"Note: the compliance score is computed for all recorded periods; it cannot be "
                    f"narrowed to {p.display}.")
    resp = GstReconciliationService.get_financial_insights(
        db=ctx.db, client_id=client.id, user=ctx.user, period=label)
    return resp, note


# ══════════════════════════════════════════════════════════════════════════════
#  7. Accounting (trial balance, P&L, balance sheet, journals)
# ══════════════════════════════════════════════════════════════════════════════

@safe_tool("accounting", "Accounting summary", "General ledger (posted journal entries)", "accounting")
def tool_accounting(ctx: ToolContext, client: Client) -> Fact:
    from app.services.financial_statements_service import FinancialStatementsService
    from app.services.trial_balance_service import TrialBalanceService

    src = "General ledger (posted journal entries)"
    f = _base(client, "accounting", "Accounting summary", src, "accounting")

    je_base = ctx.db.query(JournalEntry).filter(JournalEntry.client_id == client.id)
    posted = je_base.filter(JournalEntry.status == "posted", JournalEntry.is_reversed == False).count()  # noqa: E712
    draft_je = je_base.filter(JournalEntry.status == "draft").count()
    reversed_n = je_base.filter(JournalEntry.is_reversed == True).count()  # noqa: E712
    draft_vouchers = ctx.db.query(func.count(AccountingRecord.id)).filter(
        AccountingRecord.client_id == client.id, AccountingRecord.status == "draft").scalar() or 0

    lines = [f"Journal entries — posted {posted}, draft {draft_je}, reversed {reversed_n}; "
             f"vouchers awaiting posting: {draft_vouchers}"]

    scoped_posted = _posted_je_count(ctx, client.id)
    if scoped_posted == 0:
        scope = f" in {ctx.period.display}" if ctx.period.is_set else ""
        f.available = False
        f.note = (f"No posted journal entries exist for {client.company_name}{scope}, so the trial balance, "
                  f"profit & loss and balance sheet are not available.")
        f.lines = lines + [f.note]
        f.compact = f"no posted entries ({draft_vouchers} vouchers awaiting posting)"
        f.data = {"posted": 0}
        return f

    # Trial balance
    tb = TrialBalanceService.generate_trial_balance(
        db=ctx.db, client_id=client.id, user=ctx.user,
        as_of_date=ctx.today, **_period_args(ctx))
    hc = tb.health_check
    lines.append(f"Trial balance ({'to ' + fmt_date(tb.as_of_date) if not ctx.period.is_set else ctx.period.display}): "
                 f"debits {inr(tb.total_debit)}, credits {inr(tb.total_credit)} — "
                 f"{'balanced' if tb.is_balanced else 'NOT balanced (difference ' + inr(hc.difference) + ')'}; "
                 f"health check {hc.status}")
    if hc.unposted_drafts_count:
        lines.append(f"Unposted drafts flagged by health check: {hc.unposted_drafts_count}")

    # P&L
    if ctx.period.is_set:
        p_from, p_to = ctx.period.from_date, ctx.period.to_date
    else:
        mn = ctx.db.query(func.min(JournalEntry.entry_date)).filter(
            JournalEntry.client_id == client.id, JournalEntry.status == "posted").scalar()
        p_from, p_to = (mn or ctx.today), ctx.today
    pl = FinancialStatementsService.generate_profit_and_loss(
        db=ctx.db, client_id=client.id, user=ctx.user, from_date=p_from, to_date=p_to)
    lines.append(f"Profit & Loss ({fmt_date(p_from)} to {fmt_date(p_to)}): revenue {inr(pl.revenue_section.total)}, "
                 f"cost of sales {inr(pl.cost_of_sales_section.total)}, gross profit {inr(pl.gross_profit)}, "
                 f"operating expenses {inr(pl.total_operating_expenses)}, "
                 f"net profit before tax {inr(pl.net_profit_before_tax)}")

    # Balance sheet
    bs = FinancialStatementsService.generate_balance_sheet(
        db=ctx.db, client_id=client.id, user=ctx.user, as_of_date=ctx.period.to_date if ctx.period.is_set else ctx.today)
    lines.append(f"Balance sheet (as of {fmt_date(bs.as_of_date)}): total assets {inr(bs.total_assets)}, "
                 f"total liabilities {inr(bs.total_liabilities)}, total equity {inr(bs.total_equity)} — "
                 f"{'balanced' if bs.is_balanced else 'NOT balanced (difference ' + inr(bs.difference) + ')'}")

    # Account balances (filtered by account words in the message, else the biggest)
    msg_tokens = set(tokenize(ctx.message))
    rows = [(a, g.account_type) for g in tb.groups for a in g.accounts
            if (a.debit_balance or ZERO) != ZERO or (a.credit_balance or ZERO) != ZERO]
    mentioned = [(a, t) for a, t in rows if any(tok in msg_tokens for tok in name_tokens(a.account_name) if len(tok) >= 4)]
    show = mentioned or sorted(rows, key=lambda x: -max(x[0].debit_balance, x[0].credit_balance))[:8]
    if show:
        lines.append("Account balances" + (" (matching your question)" if mentioned else " (largest)") + ":")
        for a, _t in show[:10]:
            side = f"Dr {inr(a.debit_balance)}" if a.debit_balance else f"Cr {inr(a.credit_balance)}"
            lines.append(f"- {a.account_code} {a.account_name}: {side}")

    f.lines = lines
    f.compact = (f"revenue {inr(pl.revenue_section.total)} · net profit {inr(pl.net_profit_before_tax)} · "
                 f"TB {'balanced' if tb.is_balanced else 'unbalanced'}")
    f.data = {"posted": posted, "revenue": pl.revenue_section.total, "net_profit": pl.net_profit_before_tax,
              "balanced": tb.is_balanced}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  8. Compliance calendar / filing status / audit / notices
# ══════════════════════════════════════════════════════════════════════════════

def _next_due(today: date, day: int, quarterly: bool) -> Tuple[date, str]:
    """Next statutory due date >= today and a label for the period it covers."""
    for i in range(0, 15):
        total = (today.month - 1) + i
        yy, mm = today.year + total // 12, total % 12 + 1
        if quarterly and mm not in (1, 4, 7, 10):
            continue
        d = date(yy, mm, min(day, calendar.monthrange(yy, mm)[1]))
        if d >= today:
            # The return filed in month `mm` covers the month before it; for QRMP filers
            # (due in Jan/Apr/Jul/Oct) it covers the quarter that ended in that previous month.
            prev_m, prev_y = (mm - 1, yy) if mm > 1 else (12, yy - 1)
            covered = (f"quarter ending {calendar.month_name[prev_m]} {prev_y}" if quarterly
                       else f"{calendar.month_name[prev_m]} {prev_y}")
            return d, covered
    return today, "next period"


@safe_tool("compliance", "Compliance & filings", "GST/tax filing records & statutory calendar", "gst")
def tool_compliance(ctx: ToolContext, client: Client) -> Fact:
    f = _base(client, "compliance", "Compliance & filings", "GST/tax filing records & statutory calendar", "gst")
    quarterly = (client.return_frequency or client.billing_cycle or "").strip().lower().startswith("q")
    dues = get_settings().STATUTORY_DUE_DATES["quarterly" if quarterly else "monthly"]

    lines = [f"Return filing frequency: {'Quarterly' if quarterly else 'Monthly'}"]
    d1, c1 = _next_due(ctx.today, dues["GSTR-1"], quarterly)
    d3, c3 = _next_due(ctx.today, dues["GSTR-3B"], quarterly)
    lines.append(f"Next statutory due dates: GSTR-1 for {c1} on {fmt_date(d1)}; GSTR-3B for {c3} on {fmt_date(d3)} "
                 f"(per the due-date schedule configured in FinLedger)")

    gst_rows = (ctx.db.query(GSTRecord).filter(GSTRecord.client_id == client.id)
                .order_by(GSTRecord.due_date.desc().nullslast()).limit(6).all())
    overdue = 0
    if gst_rows:
        lines.append("GST filing records:")
        for g in gst_rows:
            st = (g.filing_status or "pending").lower()
            is_overdue = st in ("pending", "overdue") and g.due_date is not None and g.due_date < ctx.today
            overdue += 1 if is_overdue else 0
            lines.append(f"- {g.gst_type} · period {g.gst_period} · "
                         f"{'OVERDUE' if is_overdue else st.title()} · due {fmt_date(g.due_date)}"
                         + (f" · tax {inr(g.total_tax)}" if g.total_tax else ""))
    else:
        lines.append("No GST filing records are on file.")

    tax_rows = (ctx.db.query(TaxRecord).filter(TaxRecord.client_id == client.id)
                .order_by(TaxRecord.financial_year.desc()).limit(4).all())
    if tax_rows:
        lines.append("Income-tax / TDS records (as recorded in the workspace):")
        for t in tax_rows:
            lines.append(f"- FY {t.financial_year} · {t.tax_type.replace('_', ' ')} · {t.status} · "
                         f"taxable income {inr(t.taxable_income)} · TDS {inr(t.tds)} · "
                         f"advance tax {inr(t.advance_tax)} · total tax {inr(t.total_tax)}")

    audits = (ctx.db.query(AuditReport).filter(AuditReport.client_id == client.id)
              .order_by(AuditReport.created_at.desc()).limit(3).all())
    flagged = 0
    if audits:
        lines.append("Audit status:")
        for a in audits:
            flagged += 1 if (a.audit_status or "").lower() == "flagged" else 0
            risk = f" · risk score {a.risk_score}/100" if a.risk_score is not None else ""
            lines.append(f"- {a.audit_type} audit · {a.audit_status}{risk}"
                         + (f" · findings: {a.findings[:140]}" if a.findings else ""))

    notices = (ctx.db.query(UploadedDocument).filter(
        UploadedDocument.client_id == client.id, UploadedDocument.document_category == "gst_notice",
        UploadedDocument.status != "rejected").order_by(UploadedDocument.uploaded_at.desc()).limit(5).all())
    if notices:
        lines.append("GST notices on file:")
        for n in notices:
            lines.append(f"- Notice {n.notice_number or 'no number'} · dated {n.notice_date or 'n/a'} · "
                         f"response due {n.response_due_date or 'not captured'} · priority {n.priority or 'n/a'}")

    f.lines = lines
    f.compact = (f"{overdue} overdue GST filing(s) · next GSTR-3B due {fmt_date(d3)}"
                 + (f" · {flagged} audit flagged" if flagged else ""))
    f.data = {"overdue": overdue, "flagged": flagged, "next_3b": d3, "notices": len(notices)}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  Workspace-level tools (no single client)
# ══════════════════════════════════════════════════════════════════════════════

def tool_workspace_list(ctx: ToolContext, clients: List[Client]) -> Fact:
    f = Fact(key="workspace_list", title="Your clients", source="Client master records",
             link="/app/workspace")
    n = len(clients)
    if n == 0:
        f.available = False
        f.note = "Your workspace has no clients yet."
        f.lines = [f.note]
        return f
    risk = Counter((c.risk_level or "unknown").lower() for c in clients)
    status = Counter((c.status or "unknown").lower() for c in clients)
    lines = [f"Total clients in workspace: {n}",
             "By risk — " + " · ".join(f"{k.title()}: {v}" for k, v in sorted(risk.items())),
             "By status — " + " · ".join(f"{k.title()}: {v}" for k, v in sorted(status.items())),
             "Clients:"]
    for c in clients[:40]:
        lines.append(f"- {c.client_code} — {c.company_name} · {(c.client_type or '').title()} · "
                     f"{(c.risk_level or 'unknown').title()} risk · {(c.status or 'unknown').title()}"
                     + (f" · GSTIN {c.gst_number}" if c.gst_number else ""))
    if n > 40:
        lines.append(f"…and {n - 40} more.")
    f.lines = lines
    f.data = {"total": n}
    return f


def tool_workspace_attention(ctx: ToolContext, clients: List[Client]) -> Fact:
    """Rank clients by explainable, rule-based signals (no scoring model)."""
    f = Fact(key="workspace_attention", title="Clients needing attention",
             source="Workspace roll-up (risk level, filings, documents, audits, drafts)", link="/app/workspace")
    if not clients:
        f.available = False
        f.note = "Your workspace has no clients yet."
        f.lines = [f.note]
        return f
    ids = [c.id for c in clients]
    db = ctx.db

    unverified = dict(db.query(UploadedDocument.client_id, func.count(UploadedDocument.id)).filter(
        UploadedDocument.client_id.in_(ids), UploadedDocument.status.notin_(("verified", "rejected"))
    ).group_by(UploadedDocument.client_id).all())
    drafts = dict(db.query(JournalEntry.client_id, func.count(JournalEntry.id)).filter(
        JournalEntry.client_id.in_(ids), JournalEntry.status == "draft").group_by(JournalEntry.client_id).all())
    overdue = dict(db.query(GSTRecord.client_id, func.count(GSTRecord.id)).filter(
        GSTRecord.client_id.in_(ids), GSTRecord.filing_status.in_(("pending", "overdue")),
        GSTRecord.due_date < ctx.today).group_by(GSTRecord.client_id).all())
    flagged = dict(db.query(AuditReport.client_id, func.count(AuditReport.id)).filter(
        AuditReport.client_id.in_(ids), AuditReport.audit_status == "flagged").group_by(AuditReport.client_id).all())
    notices = dict(db.query(UploadedDocument.client_id, func.count(UploadedDocument.id)).filter(
        UploadedDocument.client_id.in_(ids), UploadedDocument.document_category == "gst_notice",
        UploadedDocument.status != "rejected").group_by(UploadedDocument.client_id).all())

    ranked = []
    for c in clients:
        reasons: List[str] = []
        score = 0
        rl = (c.risk_level or "").lower()
        if rl == "high":
            score += 3; reasons.append("high risk level")
        elif rl == "medium":
            score += 1; reasons.append("medium risk level")
        if overdue.get(c.id):
            score += 3; reasons.append(f"{overdue[c.id]} overdue GST filing(s)")
        if flagged.get(c.id):
            score += 2; reasons.append(f"{flagged[c.id]} flagged audit(s)")
        if notices.get(c.id):
            score += 2; reasons.append(f"{notices[c.id]} GST notice(s) on file")
        if unverified.get(c.id):
            score += 1; reasons.append(f"{unverified[c.id]} document(s) awaiting verification")
        if drafts.get(c.id):
            score += 1; reasons.append(f"{drafts[c.id]} draft journal entr{'ies' if drafts[c.id] > 1 else 'y'}")
        if score:
            ranked.append((score, c, reasons))
    ranked.sort(key=lambda x: (-x[0], (x[1].company_name or "").lower()))

    risk = Counter((c.risk_level or "unknown").lower() for c in clients)
    lines = [f"Clients in workspace: {len(clients)} — " + " · ".join(f"{k.title()} risk: {v}" for k, v in sorted(risk.items()))]
    if not ranked:
        lines.append("No client currently has an open risk signal (no overdue filings, flagged audits, notices, "
                     "unverified documents or draft entries).")
    else:
        lines.append("Clients needing attention (most urgent first):")
        for _s, c, reasons in ranked[:15]:
            lines.append(f"- {c.client_code} — {c.company_name}: " + "; ".join(reasons))
    lines.append("Signals used: risk level, overdue GST filing records, flagged audits, GST notices, "
                 "unverified documents, draft journal entries.")
    f.lines = lines
    f.data = {"flagged_clients": len(ranked)}
    return f


# ══════════════════════════════════════════════════════════════════════════════
#  Multi-client helpers
# ══════════════════════════════════════════════════════════════════════════════

def run_per_client(ctx: ToolContext, tool: Callable[..., Fact], clients: Iterable[Client],
                   *args, max_clients: int = 25) -> Tuple[List[Fact], List[str]]:
    """Run a client tool over several clients within the time budget."""
    facts: List[Fact] = []
    notes: List[str] = []
    clients = list(clients)
    for idx, c in enumerate(clients):
        if idx >= max_clients:
            notes.append(f"Only the first {max_clients} of {len(clients)} clients were analysed.")
            break
        if ctx.out_of_time:
            notes.append(f"Time budget reached — analysed {idx} of {len(clients)} clients.")
            break
        facts.append(tool(ctx, c, *args))
    return facts, notes


def aggregate_totals(facts: List[Fact], key: str) -> Optional[Fact]:
    """Deterministic roll-up (pure addition of verified per-client numbers)."""
    ok = [f for f in facts if f.key == key and f.available and f.data]
    if len(ok) < 2:
        return None
    agg = Fact(key=f"{key}_total", title="Workspace total", source="Sum of per-client verified figures")
    if key == "gst":
        out = sum((f.data["output_tax"] for f in ok), ZERO)
        itc = sum((f.data["net_itc"] for f in ok), ZERO)
        cash = sum((f.data["cash_payable"] for f in ok), ZERO)
        agg.lines = [f"Combined across {len(ok)} client(s): output tax {inr(out)}, net ITC {inr(itc)}, "
                     f"cash GST payable {inr(cash)}"]
    elif key == "discrepancies":
        tot = sum(f.data["total"] for f in ok)
        high = sum(f.data["high"] for f in ok)
        risk = sum((to_decimal(f.data.get("tax_at_risk")) or ZERO for f in ok), ZERO)
        agg.lines = [f"Combined across {len(ok)} client(s): {tot} discrepancies ({high} high severity), "
                     f"tax at risk {inr(risk)}"]
    elif key == "itc":
        el = sum((f.data["eligible"] for f in ok), ZERO)
        lg = sum((f.data["ledger"] for f in ok), ZERO)
        agg.lines = [f"Combined across {len(ok)} client(s): eligible ITC {inr(el)}, ITC booked in ledger {inr(lg)}"]
    elif key == "documents":
        tot = sum(f.data["total"] for f in ok)
        unv = sum(f.data["unverified"] for f in ok)
        agg.lines = [f"Combined across {len(ok)} client(s): {tot} documents, {unv} awaiting verification"]
    else:
        return None
    return agg
