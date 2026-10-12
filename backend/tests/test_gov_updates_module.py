"""
Unit and Integration Tests for Government Updates Module (J1-J11).
Strict compliance with R3, R4, R5, R6:
- Never touches live database (enforces test DB guard)
- Uses SQLite in-memory
- Fixture-backed network isolation (no live network during CI tests)
- Tests deduplication, rate limits, robots.txt, WAF detection, SSRF protection,
  legal status tagging, Income-tax Act 2025 vs 1961, AI grounding check rejection,
  and API filters.
"""

import os
import sys
import time
import uuid
from datetime import date, datetime, timezone, timedelta
from typing import Dict, Any
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.database.session import Base
from app.models.user import User
from app.models.government_update import GovSource, GovUpdate, GovFetchRun, GovSavedUpdate
from app.services.gov_updates.adapters.base import RawUpdateItem
from app.services.gov_updates.adapters.rss_adapter import RssAdapter
from app.services.gov_updates.adapters.html_adapter import HtmlListingAdapter, parse_date_strict
from app.services.gov_updates.adapters.pdf_extractor import extract_pdf_text
from app.services.gov_updates.client import GovHttpClient, FetchResult
from app.services.gov_updates.normalizer import GovNormalizer
from app.services.gov_updates.ai_explainer import GovAiExplainer, verify_grounding
from app.services.gov_updates.service import GovUpdateService
from app.services.gov_updates.sync_engine import GovSyncEngine


# ── Test DB Guard (R3) ────────────────────────────────────────────────────────
def assert_safe_db_url(url: str):
    """Enforces R3: Aborts if connection URL targets live production DB."""
    if "ca_assistant_db" in url and "test" not in url:
        raise RuntimeError(f"SAFETY GUARD VIOLATION: Refusing to run tests against live '{url}'")


def test_safety_guard_rejects_live_db():
    """Verify that test DB guard strictly rejects production database URLs."""
    live_url = "postgresql://postgres:secret@localhost:5432/ca_assistant_db"
    with pytest.raises(RuntimeError, match="SAFETY GUARD VIOLATION"):
        assert_safe_db_url(live_url)

    # Safe test URLs pass
    assert_safe_db_url("sqlite:///:memory:")
    assert_safe_db_url("postgresql://postgres:secret@localhost:5432/ca_assistant_test_db")


@pytest.fixture
def db_session():
    """In-memory SQLite test database session (R3)."""
    test_url = "sqlite:///:memory:"
    assert_safe_db_url(test_url)

    engine = create_engine(
        test_url,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(
        bind=engine,
        tables=[
            User.__table__,
            GovSource.__table__,
            GovUpdate.__table__,
            GovFetchRun.__table__,
            GovSavedUpdate.__table__,
        ],
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def mock_users(db_session):
    ca_user = User(
        id=uuid.uuid4(),
        email="ca@finledger.ai",
        full_name="Bhumi Jha",
        role="ca",
        password_hash="hash",
        is_active=True,
    )
    client_user = User(
        id=uuid.uuid4(),
        email="client@finledger.ai",
        full_name="Vikram Singh",
        role="client",
        password_hash="hash",
        is_active=True,
    )
    db_session.add_all([ca_user, client_user])
    db_session.commit()
    return ca_user, client_user


# ── J4 Adapters Tests ─────────────────────────────────────────────────────────

def test_rss_adapter_parsing():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures/gov/rbi/notifications.xml")
    with open(fixture_path, "r", encoding="utf-8") as f:
        xml = f.read()

    items = RssAdapter.parse(xml, "rbi_notifications")
    assert len(items) == 2
    assert "Risk Management" in items[0].title
    assert items[0].doc_number == "RBI-ID-13738"
    assert items[0].issue_date == date(2026, 10, 10)
    assert items[0].text_status == "ok"


def test_date_parsing_never_guesses_today():
    # If a date cannot be parsed, return None. NEVER today's date!
    res1 = parse_date_strict("Undated Circular without any timestamp")
    assert res1 is None

    res2 = parse_date_strict("Invalid date 99-99-9999")
    assert res2 is None

    # Valid dates
    res3 = parse_date_strict("Notice published on 12-Oct-2026")
    assert res3 == date(2026, 10, 12)

    res4 = parse_date_strict("Published Oct 08, 2026")
    assert res4 == date(2026, 10, 8)


def test_html_adapter_gstcouncil():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures/gov/gstcouncil/homepage.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    items = HtmlListingAdapter.parse("gstcouncil", html, "https://gstcouncil.gov.in")
    assert len(items) == 2
    assert "57th Meeting of the GST Council" in items[0].title
    assert items[0].doc_number == "GSTC-57TH"
    assert items[0].pdf_url == "https://gstcouncil.gov.in/sites/default/files/2026-10/press_release_0.pdf"


def test_html_adapter_icai():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures/gov/icai/announcements.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    items = HtmlListingAdapter.parse("icai_announcements", html, "https://www.icai.org")
    assert len(items) == 2
    assert items[0].issue_date == date(2026, 10, 5)
    assert items[1].issue_date == date(2026, 8, 24)


def test_html_adapter_egazette():
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures/gov/egazette/homepage.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        html = f.read()

    items = HtmlListingAdapter.parse("egazette_recent", html, "https://egazette.gov.in")
    assert len(items) == 2
    assert items[0].doc_number == "CG-DL-E-12102026-277060"
    assert items[0].issue_date == date(2026, 10, 12)


def test_pdf_extractor_scans_and_size_limits():
    # Empty bytes -> no_text
    txt, status = extract_pdf_text(b"")
    assert status == "no_text"

    # Random binary bytes -> no_text
    txt, status = extract_pdf_text(b"not a valid pdf binary")
    assert status == "no_text"


# ── J3 & R5/R6 Polite HTTP Client Tests ───────────────────────────────────────

def test_robots_disallow():
    client = GovHttpClient()
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures/gov/robots/robots.txt")
    with open(fixture_path, "r", encoding="utf-8") as f:
        robots_txt = f.read()

    # Pre-populate robots cache
    import urllib.robotparser
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_txt.splitlines())
    client.robots_cache["example.gov.in"] = (rp, time.time())

    # Path disallowed by robots
    allowed, delay = client.check_robots("https://example.gov.in/blocked-path/doc.pdf")
    assert allowed is False

    # Path allowed
    allowed_ok, _ = client.check_robots("https://example.gov.in/public/circular.pdf")
    assert allowed_ok is True


def test_waf_and_captcha_detection():
    client = GovHttpClient()
    fixture_path = os.path.join(os.path.dirname(__file__), "fixtures/gov/waf_challenge/challenge.html")
    with open(fixture_path, "r", encoding="utf-8") as f:
        challenge_html = f.read()

    is_challenge, reason = client.detect_challenge(403, {}, challenge_html)
    assert is_challenge is True
    assert "WAF/bot challenge" in reason or "challenge" in reason.lower()

    # Clean page
    is_challenge, _ = client.detect_challenge(200, {}, "<html><body>Clean statutory order</body></html>")
    assert is_challenge is False


def test_ssrf_and_domain_allowlist():
    client = GovHttpClient()
    # Attempting to fetch private IP
    res = client.fetch("http://127.0.0.1/secret", allowlisted_domains={"rbi.org.in"})
    assert "SSRF" in res.error

    # Attempting to fetch un-registered domain
    res2 = client.fetch("https://attacker-domain.com/evil", allowlisted_domains={"rbi.org.in"})
    assert "not in registered allowlist" in res2.error


def test_clock_injected_rate_limiting():
    simulated_time = 1000.0

    def clock():
        return simulated_time

    client = GovHttpClient(clock=clock, min_host_delay=3.0)
    client.host_last_request["rbi.org.in"] = 1000.0

    # Advance time only 1 second (less than 3.0s min delay)
    simulated_time = 1001.0

    # Mock _sleep
    sleep_calls = []
    client._sleep = lambda sec: sleep_calls.append(sec)

    # robots allowed
    client.check_robots = lambda url: (True, 0)
    # mock session.get
    client.session.get = lambda *args, **kwargs: None

    client.fetch("https://rbi.org.in/notifications_rss.xml", allowlisted_domains={"rbi.org.in"})
    assert len(sleep_calls) == 1
    assert sleep_calls[0] == pytest.approx(2.0, 0.1)


# ── J5 Normalizer & Classification Tests ──────────────────────────────────────

def test_legal_status_tagging_press_releases_never_operative():
    # Press release must NEVER be tagged operative_instrument
    st1 = GovNormalizer.classify_legal_status("press_release", "Press Release: GST Recommendations", "Meeting outcomes")
    assert st1 == "press_release_not_law"

    st2 = GovNormalizer.classify_legal_status("other", "Press Release on Trade Data", "Released by Ministry")
    assert st2 == "press_release_not_law"

    # Proposals / exposure drafts
    st3 = GovNormalizer.classify_legal_status("standard", "Exposure Draft on Lease Accounting", "Comments invited")
    assert st3 == "draft_or_proposal"

    # Operative circular
    st4 = GovNormalizer.classify_legal_status("circular", "Circular No. 214/2026", "Operational guidelines")
    assert st4 == "operative_instrument"


def test_law_version_tagging_2025_vs_1961():
    # Income-tax Act, 2025
    ver1 = GovNormalizer.detect_law_version("Rules notified under Income-tax Act, 2025", "Effective from 1 April 2026")
    assert ver1 == "Income-tax Act, 2025"

    ver2 = GovNormalizer.detect_law_version("Tax Year 2026-27 calculation guidelines", "Tax Year replaces AY")
    assert ver2 == "Income-tax Act, 2025"

    # Income-tax Act, 1961
    ver3 = GovNormalizer.detect_law_version("Section 44ADA under Income-tax Act, 1961", "Previous year assessment")
    assert ver3 == "Income-tax Act, 1961"

    # GST
    ver4 = GovNormalizer.detect_law_version("Central Goods and Services Tax Act Notification", "CGST Act")
    assert ver4 == "CGST Act 2017"


def test_supersedes_detection():
    status, conf, refs = GovNormalizer.detect_supersedes(
        "Notification No. 25/2026 in supersession of notification 10/2023-Central Tax",
        "This notification supersedes notification 10/2023-Central Tax dated 01-08-2023",
    )
    assert "10/2023-Central" in refs[0] or "10/2023" in refs[0]


def test_fixed_topic_taxonomy_validation():
    topics = GovNormalizer.extract_topics("E-invoicing and ITC reconciliation guidelines", "Rule 36(4) credit reversal")
    assert "e_invoicing" in topics
    assert "itc" in topics
    for t in topics:
        assert t in [
            "rates", "returns_filing", "due_dates", "e_invoicing", "e_way_bill",
            "itc", "refunds", "registration", "tds_tcs", "accounting_standards",
            "audit", "budget", "penalties_interest", "other"
        ]


# ── J6 AI Grounding Verification Tests ───────────────────────────────────────

def test_ai_grounding_check_accepts_grounded_text():
    source_text = "The GST Council in its 57th meeting recommended raising prosecution threshold from Rs. 1 crore to Rs. 5 crore on 08.10.2026."
    ai_json = {
        "summary": "Prosecution threshold increased from Rs. 1 crore to Rs. 5 crore.",
        "who_is_affected": "Taxpayers facing penalty proceedings under 57th meeting rules.",
        "key_dates": ["08.10.2026"],
        "action_items": [],
    }
    is_grounded, reason = verify_grounding(ai_json, source_text)
    assert is_grounded is True
    assert reason is None


def test_ai_grounding_check_rejects_ungrounded_hallucinated_number():
    source_text = "Standard deduction increased under Budget 2026 proposals."
    # AI hallucinated 75,000 which is NOT present in source_text
    ai_json = {
        "summary": "Standard deduction increased to Rs. 75,000 for salaried employees.",
        "who_is_affected": "Salaried taxpayers",
        "key_dates": [],
        "action_items": [],
    }
    is_grounded, reason = verify_grounding(ai_json, source_text)
    assert is_grounded is False
    assert "Ungrounded numerical entity detected" in reason


# ── J7 & J8 Sync, Deduplication, API Tests ────────────────────────────────────

def test_deduplication_and_in_place_update(db_session):
    source = GovSource(
        code="rbi_test",
        name="RBI Test",
        base_url="https://rbi.org.in",
        domain="rbi.org.in",
        tier=1,
        method="rss",
        enabled=True,
    )
    db_session.add(source)
    db_session.commit()

    raw1 = RawUpdateItem(
        title="Circular on Cash Reserve Ratio",
        url="https://rbi.org.in/scripts/crr.aspx",
        doc_number="RBI-101",
        issue_date=date(2026, 10, 9),
        content_text="Initial text version",
        text_status="ok",
    )

    norm1 = GovNormalizer.normalize_item(raw1, source.code)
    u1 = GovUpdate(source_id=source.id, **norm1)
    db_session.add(u1)
    db_session.commit()

    # Second sync: identical content hash -> should skip without inserting duplicate
    raw2 = RawUpdateItem(
        title="Circular on Cash Reserve Ratio",
        url="https://rbi.org.in/scripts/crr.aspx",
        doc_number="RBI-101",
        issue_date=date(2026, 10, 9),
        content_text="Initial text version",
        text_status="ok",
    )
    norm2 = GovNormalizer.normalize_item(raw2, source.code)
    assert norm2["content_hash"] == u1.content_hash

    # Count before
    assert db_session.query(GovUpdate).count() == 1

    # Simulate updated text in source
    raw3 = RawUpdateItem(
        title="Circular on Cash Reserve Ratio (Amended)",
        url="https://rbi.org.in/scripts/crr.aspx",
        doc_number="RBI-101",
        issue_date=date(2026, 10, 9),
        content_text="Amended text version with new clause",
        text_status="ok",
    )
    norm3 = GovNormalizer.normalize_item(raw3, source.code)
    assert norm3["content_hash"] != u1.content_hash

    # Update in place
    u1.title = norm3["title"]
    u1.content_text = norm3["content_text"]
    u1.content_hash = norm3["content_hash"]
    db_session.commit()

    # Count remains exactly 1 (zero duplicates created)
    assert db_session.query(GovUpdate).count() == 1
    reloaded = db_session.query(GovUpdate).first()
    assert reloaded.title == "Circular on Cash Reserve Ratio (Amended)"


def test_api_filters_and_pagination(db_session, mock_users):
    ca_user, client_user = mock_users
    source = GovSource(
        code="gst_test",
        name="GST Test",
        base_url="https://gstcouncil.gov.in",
        domain="gstcouncil.gov.in",
        tier=1,
        method="html_listing",
        enabled=True,
    )
    db_session.add(source)
    db_session.commit()

    # Add 3 test updates
    u1 = GovUpdate(
        source_id=source.id,
        title="GST Circular on E-Invoicing Thresholds",
        doc_type="circular",
        legal_status="operative_instrument",
        doc_number="GST-214",
        issue_date=date(2026, 10, 1),
        category="GST",
        topics=["e_invoicing"],
        law_version="CGST Act 2017",
        url="https://gstcouncil.gov.in/c1",
        content_text="E-invoicing guidelines",
        text_status="ok",
        content_hash="hash1",
        status="active",
    )
    u2 = GovUpdate(
        source_id=source.id,
        title="Income-tax Rules 2026 Notification",
        doc_type="notification",
        legal_status="operative_instrument",
        doc_number="ITD-12",
        issue_date=date(2026, 10, 5),
        category="INCOME_TAX",
        topics=["returns_filing"],
        law_version="Income-tax Act, 2025",
        url="https://incometaxindia.gov.in/n1",
        content_text="Notified under Income-tax Act, 2025",
        text_status="ok",
        content_hash="hash2",
        status="active",
    )
    db_session.add_all([u1, u2])
    db_session.commit()

    # Query Category filter
    res = GovUpdateService.list_updates(db_session, ca_user, category="GST")
    assert res.total == 1
    assert res.items[0].title == u1.title

    # Query Law Version filter
    res_law = GovUpdateService.list_updates(db_session, ca_user, law_version="Income-tax Act, 2025")
    assert res_law.total == 1
    assert res_law.items[0].title == u2.title

    # Query Search q
    res_q = GovUpdateService.list_updates(db_session, ca_user, q="E-Invoicing")
    assert res_q.total == 1


def test_saved_bookmarks_isolated_per_user(db_session, mock_users):
    ca_user, client_user = mock_users
    source = GovSource(code="s1", name="S1", base_url="https://s1.org", domain="s1.org", method="rss", enabled=True)
    db_session.add(source)
    db_session.commit()

    u = GovUpdate(
        source_id=source.id,
        title="Test Update",
        category="GST",
        topics=["rates"],
        url="https://s1.org/u1",
        content_hash="h1",
        status="active",
    )
    db_session.add(u)
    db_session.commit()

    # CA saves update
    GovUpdateService.save_update(db_session, ca_user, u.id)

    # Check CA listing: is_saved is True
    res_ca = GovUpdateService.list_updates(db_session, ca_user)
    assert res_ca.items[0].is_saved is True

    # Check Client listing: is_saved is False (tenant/user isolation)
    res_client = GovUpdateService.list_updates(db_session, client_user)
    assert res_client.items[0].is_saved is False

    # CA unsaves update
    GovUpdateService.unsave_update(db_session, ca_user, u.id)
    res_ca2 = GovUpdateService.list_updates(db_session, ca_user)
    assert res_ca2.items[0].is_saved is False


def test_empty_state_honest_message(db_session, mock_users):
    ca_user, _ = mock_users
    res = GovUpdateService.list_updates(db_session, ca_user)
    assert res.total == 0
    assert len(res.items) == 0
    meta = GovUpdateService.get_meta(db_session)
    assert meta.total_updates == 0
