"""
Seed Script — Populates PostgreSQL with realistic sample data.

20 clients × full financial records across all 10 tables.

Usage:
    cd backend
    python -m app.seed
"""

import random
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from sqlalchemy.orm import Session

from app.database.session import engine, Base, SessionLocal
from app.core.security import hash_password
from app.models.user import User
from app.models.client import Client
from app.models.accounting_record import AccountingRecord
from app.models.gst_record import GSTRecord
from app.models.tax_record import TaxRecord
from app.models.audit_report import AuditReport
from app.models.invoice import Invoice
from app.models.document import Document
from app.models.government_rule import GovernmentRule
from app.models.notification import Notification

random.seed(42)  # reproducible data


def _rdate(y0: int = 2024, y1: int = 2026) -> date:
    start, end = date(y0, 1, 1), date(y1, 6, 30)
    return start + timedelta(days=random.randint(0, (end - start).days))


def _revenue() -> Decimal:
    return Decimal(str(round(random.uniform(500_000, 5_00_00_000), 2)))


CLIENTS = [
    (
        "CLI-001",
        "Tata Consultancy Services",
        "company",
        "Rajesh Gopinathan",
        "finance@tcs.com",
        "+91-22-67789999",
        "27AAACT2727Q1ZV",
        "AAACT2727Q",
        "TCS House, Fort, Mumbai",
        "Mumbai",
        "Maharashtra",
        "low",
        "active",
    ),
    (
        "CLI-002",
        "Reliance Industries Ltd",
        "company",
        "Alok Agarwal",
        "accounts@ril.com",
        "+91-22-35553555",
        "27AAACR5055K1ZY",
        "AAACR5055K",
        "Maker Chambers, Nariman Point",
        "Mumbai",
        "Maharashtra",
        "low",
        "active",
    ),
    (
        "CLI-003",
        "Infosys Limited",
        "company",
        "Nilanjan Roy",
        "cfo@infosys.com",
        "+91-80-28520261",
        "29AABCI1234L1ZP",
        "AABCI1234L",
        "Electronics City, Bangalore",
        "Bangalore",
        "Karnataka",
        "low",
        "active",
    ),
    (
        "CLI-004",
        "Bharti Airtel Limited",
        "company",
        "Harjeet Kohli",
        "finance@airtel.com",
        "+91-11-46666100",
        "07AABCB1234M1Z5",
        "AABCB1234M",
        "Udyog Vihar, Gurgaon",
        "Gurgaon",
        "Haryana",
        "medium",
        "active",
    ),
    (
        "CLI-005",
        "Wipro Technologies",
        "company",
        "Jatin Dalal",
        "accounts@wipro.com",
        "+91-80-28440011",
        "29AABCW1234N1ZQ",
        "AABCW1234N",
        "Sarjapur Road, Bangalore",
        "Bangalore",
        "Karnataka",
        "low",
        "active",
    ),
    (
        "CLI-006",
        "Mahindra & Mahindra",
        "company",
        "Manoj Bhat",
        "finance@mahindra.com",
        "+91-22-28462500",
        "27AABCM5678P1Z3",
        "AABCM5678P",
        "Gateway Building, Mumbai",
        "Mumbai",
        "Maharashtra",
        "medium",
        "active",
    ),
    (
        "CLI-007",
        "Sharma & Associates LLP",
        "llp",
        "Vikram Sharma",
        "vikram@sharmaassociates.in",
        "+91-11-23456789",
        "07AAFFS1234R1Z8",
        "AAFFS1234R",
        "Connaught Place, New Delhi",
        "New Delhi",
        "Delhi",
        "low",
        "active",
    ),
    (
        "CLI-008",
        "Patel Textiles Pvt Ltd",
        "company",
        "Amit Patel",
        "amit@pateltextiles.com",
        "+91-79-26578900",
        "24AABCP6789S1Z2",
        "AABCP6789S",
        "Ring Road, Surat",
        "Surat",
        "Gujarat",
        "high",
        "active",
    ),
    (
        "CLI-009",
        "Chennai Spices Export",
        "company",
        "Lakshmi Narayanan",
        "lakshmi@chennaispices.com",
        "+91-44-28173456",
        "33AABCC4567T1Z9",
        "AABCC4567T",
        "T Nagar, Chennai",
        "Chennai",
        "Tamil Nadu",
        "medium",
        "active",
    ),
    (
        "CLI-010",
        "Gupta Hardware Store",
        "individual",
        "Rajendra Gupta",
        "rajendra@guptahardware.com",
        "+91-522-2345678",
        "09AABPG1234U1Z4",
        "AABPG1234U",
        "Hazratganj, Lucknow",
        "Lucknow",
        "Uttar Pradesh",
        "low",
        "active",
    ),
    (
        "CLI-011",
        "Bangalore Tech Solutions",
        "company",
        "Priya Venkatesh",
        "priya@blrtech.co.in",
        "+91-80-41234567",
        "29AABCB9012V1Z1",
        "AABCB9012V",
        "Whitefield, Bangalore",
        "Bangalore",
        "Karnataka",
        "low",
        "active",
    ),
    (
        "CLI-012",
        "Kolkata Steel Industries",
        "company",
        "Debashish Roy",
        "debashish@kolkatasteel.com",
        "+91-33-22345678",
        "19AABCK3456W1Z7",
        "AABCK3456W",
        "Park Street, Kolkata",
        "Kolkata",
        "West Bengal",
        "high",
        "active",
    ),
    (
        "CLI-013",
        "Jaipur Handicrafts Co-op",
        "partnership",
        "Sunita Meena",
        "sunita@jaipurcraft.in",
        "+91-141-2567890",
        "08AABCJ7890X1Z6",
        "AABCJ7890X",
        "MI Road, Jaipur",
        "Jaipur",
        "Rajasthan",
        "medium",
        "active",
    ),
    (
        "CLI-014",
        "Hyderabad Pharma Ltd",
        "company",
        "Dr. Ravi Kumar",
        "ravi@hydpharma.com",
        "+91-40-23456789",
        "36AABCH2345Y1Z3",
        "AABCH2345Y",
        "Banjara Hills, Hyderabad",
        "Hyderabad",
        "Telangana",
        "low",
        "active",
    ),
    (
        "CLI-015",
        "Pune Agritech Solutions",
        "company",
        "Sachin Kulkarni",
        "sachin@puneagritech.com",
        "+91-20-24567890",
        "27AABCP5678Z1Z0",
        "AABCP5678Z",
        "Hinjewadi IT Park, Pune",
        "Pune",
        "Maharashtra",
        "medium",
        "pending",
    ),
    (
        "CLI-016",
        "Delhi Construction Corp",
        "company",
        "Mohit Bansal",
        "mohit@delhiconstruction.in",
        "+91-11-45678901",
        "07AABCD9012A1Z5",
        "AABCD9012A",
        "Nehru Place, New Delhi",
        "New Delhi",
        "Delhi",
        "high",
        "active",
    ),
    (
        "CLI-017",
        "Kerala Tourism Ventures",
        "partnership",
        "Anand Menon",
        "anand@keralatourism.biz",
        "+91-484-2567890",
        "32AABCK3456B1Z8",
        "AABCK3456B",
        "MG Road, Kochi",
        "Kochi",
        "Kerala",
        "low",
        "active",
    ),
    (
        "CLI-018",
        "Ahmedabad Chemicals Ltd",
        "company",
        "Hemant Shah",
        "hemant@amdchemicals.com",
        "+91-79-26789012",
        "24AABCA7890C1Z4",
        "AABCA7890C",
        "Ashram Road, Ahmedabad",
        "Ahmedabad",
        "Gujarat",
        "high",
        "active",
    ),
    (
        "CLI-019",
        "Nagpur Logistics Partners",
        "llp",
        "Deepak Rathod",
        "deepak@nagpurlogistics.co.in",
        "+91-712-2456789",
        "27AABCN1234D1Z1",
        "AABCN1234D",
        "Sitabuldi, Nagpur",
        "Nagpur",
        "Maharashtra",
        "medium",
        "inactive",
    ),
    (
        "CLI-020",
        "Chandigarh EdTech Pvt Ltd",
        "company",
        "Neha Kapoor",
        "neha@chdedtech.com",
        "+91-172-2789012",
        "04AABCC5678E1Z7",
        "AABCC5678E",
        "Sector 17, Chandigarh",
        "Chandigarh",
        "Punjab",
        "low",
        "active",
    ),
]

VOUCHER_TYPES = ["receipt", "payment", "journal", "sales", "purchase", "contra"]
CATEGORIES = [
    "salary",
    "rent",
    "utilities",
    "sales revenue",
    "tax",
    "raw material",
    "software",
    "marketing",
    "misc",
]
GST_TYPES = ["GSTR-1", "GSTR-3B", "GSTR-9", "GSTR-9C"]
GST_STATUSES = ["filed", "filed", "filed", "pending", "overdue"]
TAX_TYPES = ["income_tax", "tds", "advance_tax", "corporate_tax"]
TAX_STATUSES = ["filed", "filed", "pending", "overdue", "exempt"]
AUDIT_TYPES = ["statutory", "internal", "tax", "gst", "forensic"]
AUDIT_STATUSES = ["completed", "completed", "pending", "in_progress", "flagged"]
DOC_TYPES = ["pdf", "pdf", "image", "excel", "csv"]
GOV_CATEGORIES = ["GST", "Income Tax", "TDS", "Budget", "SEBI", "RBI"]
VENDORS = [
    "Amazon Business",
    "Flipkart Wholesale",
    "Tally Solutions",
    "Zoho Books",
    "HDFC Bank",
    "ICICI Lombard",
    "HCL Technologies",
    "Godrej Industries",
    "Hindustan Unilever",
    "LIC of India",
]
FINDINGS = [
    "All records in order. No discrepancies found.",
    "Minor discrepancies in petty cash — corrective action recommended.",
    "Inventory valuation needs review. Follow-up required.",
    "Revenue recognition policy reviewed — compliant with Ind AS.",
    "3 duplicate vendor payments detected totalling ₹1.2L.",
    "Related party transactions verified. No concerns raised.",
    "Round-figure entries detected — further scrutiny advised.",
]


def seed_database():
    print("=" * 60)
    print("  SEEDING — AI-Based CA Assistant (PostgreSQL)")
    print("=" * 60)

    Base.metadata.create_all(bind=engine)
    db: Session = SessionLocal()

    try:
        if db.query(Client).count() > 0:
            print("⚠  Already seeded. Drop tables and re-run to reseed.")
            return

        # ── 1. CA User ──────────────────────────────────────────
        print("\n[1] Creating CA user...")
        user = User(
            full_name="CA Pratham Sharma",
            email="ca@example.com",
            password_hash=hash_password("password123"),
            phone="+91-98765-43210",
            role="ca",
            is_active=True,
        )
        db.add(user)
        db.flush()
        print(f"    ✅  {user.email}  /  password123")

        # ── 2. Government Rules ─────────────────────────────────
        print("\n[2] Creating government rules...")
        gov_rules_data = [
            (
                "GST",
                "E-invoicing threshold reduced to ₹5 Cr",
                "Businesses above ₹5 Cr turnover must generate e-invoices for all B2B supplies.",
                "GSTN",
                "https://gstn.org/circular/214",
                "2026-07-18",
            ),
            (
                "Income Tax",
                "Section 44ADA presumptive limit raised",
                "Presumptive taxation limit raised to ₹75 lakh for eligible professionals.",
                "CBDT",
                "https://incometax.gov.in/circular/2026-07",
                "2026-07-12",
            ),
            (
                "TDS",
                "TDS on virtual digital assets clarified",
                "CBDT clarifies 1% TDS applicability on peer-to-peer VDA transfers via exchanges.",
                "CBDT",
                "https://cbdt.gov.in/vda-tds",
                "2026-07-05",
            ),
            (
                "Budget",
                "Standard deduction increased to ₹75,000",
                "Standard deduction under the new regime increased for salaried taxpayers.",
                "Finance Ministry",
                "https://finmin.nic.in/budget2026",
                "2026-07-01",
            ),
            (
                "GST",
                "New e-way bill rules for interstate transport",
                "Updated e-way bill requirements for goods above ₹50,000 in transit.",
                "GSTN",
                "https://ewaybill.nic.in/rules2026",
                "2026-06-20",
            ),
            (
                "SEBI",
                "Mandatory ESG reporting for listed companies",
                "SEBI mandates ESG disclosures for top 1000 listed companies.",
                "SEBI",
                "https://sebi.gov.in/esg2026",
                "2026-06-15",
            ),
        ]
        for cat, title, summary, source, url, pub_str in gov_rules_data:
            db.add(
                GovernmentRule(
                    category=cat,
                    title=title,
                    summary=summary,
                    source=source,
                    source_url=url,
                    published_date=date.fromisoformat(pub_str),
                )
            )
        db.flush()
        print(f"    ✅  {len(gov_rules_data)} rules inserted")

        # ── 3. Clients + related records ───────────────────────
        print(f"\n[3] Creating {len(CLIENTS)} clients with full financial records...")
        for idx, (
            code,
            name,
            ctype,
            contact,
            email,
            phone,
            gst,
            pan,
            addr,
            city,
            state,
            risk,
            status,
        ) in enumerate(CLIENTS, 1):

            client = Client(
                client_code=code,
                company_name=name,
                client_type=ctype,
                contact_person=contact,
                email=email,
                phone=phone,
                gst_number=gst,
                pan_number=pan,
                address=addr,
                city=city,
                state=state,
                country="India",
                risk_level=risk,
                status=status,
            )
            db.add(client)
            db.flush()
            cid = client.id
            rev = _revenue()

            # Accounting records (4-8 per client)
            n_acc = random.randint(4, 8)
            for _ in range(n_acc):
                debit = Decimal(str(round(random.uniform(5000, 500000), 2)))
                credit = Decimal("0")
                if random.random() > 0.5:
                    debit, credit = Decimal("0"), debit
                db.add(
                    AccountingRecord(
                        client_id=cid,
                        transaction_date=_rdate(),
                        voucher_type=random.choice(VOUCHER_TYPES),
                        description=f"Transaction for {name}",
                        debit=debit,
                        credit=credit,
                        category=random.choice(CATEGORIES),
                    )
                )

            # GST records (2-4 per client)
            n_gst = random.randint(2, 4)
            for m in range(n_gst):
                taxable = Decimal(
                    str(round(float(rev) * random.uniform(0.05, 0.20), 2))
                )
                rate = Decimal("0.09")
                cgst = (taxable * rate).quantize(Decimal("0.01"))
                sgst = cgst
                igst = Decimal("0")
                db.add(
                    GSTRecord(
                        client_id=cid,
                        gst_period=f"2026-{(m+4):02d}",
                        gst_type=random.choice(GST_TYPES),
                        taxable_amount=taxable,
                        cgst=cgst,
                        sgst=sgst,
                        igst=igst,
                        total_tax=cgst + sgst,
                        filing_status=random.choice(GST_STATUSES),
                        due_date=date(2026, m + 4, 20),
                    )
                )

            # Tax records (1-3 per client)
            n_tax = random.randint(1, 3)
            for _ in range(n_tax):
                inc = Decimal(str(round(float(rev) * random.uniform(0.6, 0.9), 2)))
                tds = (inc * Decimal("0.10")).quantize(Decimal("0.01"))
                adv = (inc * Decimal("0.05")).quantize(Decimal("0.01"))
                db.add(
                    TaxRecord(
                        client_id=cid,
                        financial_year=random.choice(["2024-25", "2025-26"]),
                        tax_type=random.choice(TAX_TYPES),
                        taxable_income=inc,
                        tds=tds,
                        advance_tax=adv,
                        total_tax=tds + adv,
                        status=random.choice(TAX_STATUSES),
                    )
                )

            # Audit reports (1-2 per client)
            n_aud = random.randint(1, 2)
            for _ in range(n_aud):
                db.add(
                    AuditReport(
                        client_id=cid,
                        audit_type=random.choice(AUDIT_TYPES),
                        audit_status=random.choice(AUDIT_STATUSES),
                        risk_score=Decimal(str(round(random.uniform(10, 95), 2))),
                        findings=random.choice(FINDINGS),
                        recommendations="Review and rectify the identified issues within 30 days.",
                    )
                )

            # Invoices (3-6 per client)
            n_inv = random.randint(3, 6)
            for j in range(n_inv):
                inv_date = _rdate()
                db.add(
                    Invoice(
                        client_id=cid,
                        invoice_number=f"INV-{code}-{inv_date.strftime('%Y%m')}-{j+1:03d}",
                        vendor_name=random.choice(VENDORS),
                        invoice_date=inv_date,
                        amount=Decimal(str(round(random.uniform(5000, 2500000), 2))),
                        currency="INR",
                    )
                )

            # Documents (2-4 per client)
            n_doc = random.randint(2, 4)
            for j in range(n_doc):
                ftype = random.choice(DOC_TYPES)
                db.add(
                    Document(
                        client_id=cid,
                        file_name=f"{name.replace(' ','_')}_doc_{j+1}.{ftype}",
                        file_type=ftype,
                        storage_path=f"/storage/{code}/doc_{j+1}.{ftype}",
                    )
                )

            # Notifications for the CA user (1 per client)
            db.add(
                Notification(
                    user_id=user.id,
                    title=f"New activity: {name}",
                    message=f"Client {code} — {name} has been onboarded and records have been created.",
                    is_read=random.choice([True, False]),
                )
            )

            print(f"    ✅ [{idx:02d}/20] {name:<35} risk={risk:<6} status={status}")

        db.commit()

        # ── Summary ─────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("  ✅  SEED COMPLETE")
        print("=" * 60)
        print(f"  Users:               {db.query(User).count()}")
        print(f"  Clients:             {db.query(Client).count()}")
        print(f"  Accounting Records:  {db.query(AccountingRecord).count()}")
        print(f"  GST Records:         {db.query(GSTRecord).count()}")
        print(f"  Tax Records:         {db.query(TaxRecord).count()}")
        print(f"  Audit Reports:       {db.query(AuditReport).count()}")
        print(f"  Invoices:            {db.query(Invoice).count()}")
        print(f"  Documents:           {db.query(Document).count()}")
        print(f"  Government Rules:    {db.query(GovernmentRule).count()}")
        print(f"  Notifications:       {db.query(Notification).count()}")
        print("=" * 60)
        print("\n  Login: ca@example.com / password123\n")

    except Exception as exc:
        db.rollback()
        print(f"\n❌  Seed failed: {exc}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
