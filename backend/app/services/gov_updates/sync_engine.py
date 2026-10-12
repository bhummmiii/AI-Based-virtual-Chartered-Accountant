"""
Sync Engine for Government Updates Ingestion.
Strictly implements J7:
- Per-source isolated execution (one failing source never affects others)
- Rate-limited manual sync ("Sync now")
- Conditional GET and backoff
- Resumable backfill support (backfilled=True items not marked 'New')
- Source health updates (last_success_at, last_error, status)
- Audit log in gov_fetch_runs
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session

from app.models.government_update import GovSource, GovUpdate, GovFetchRun
from app.services.gov_updates.client import GovHttpClient
from app.services.gov_updates.adapters.rss_adapter import RssAdapter
from app.services.gov_updates.adapters.html_adapter import HtmlListingAdapter
from app.services.gov_updates.adapters.pdf_extractor import extract_pdf_text
from app.services.gov_updates.normalizer import GovNormalizer
from app.services.gov_updates.ai_explainer import GovAiExplainer

logger = logging.getLogger(__name__)

SOURCE_FETCH_ENDPOINTS = {
    "rbi_notifications": "https://rbi.org.in/notifications_rss.xml",
    "rbi_pressreleases": "https://rbi.org.in/pressreleases_rss.xml",
    "gstcouncil": "https://gstcouncil.gov.in",
    "icai_announcements": "https://www.icai.org/category/announcements",
    "egazette_recent": "https://egazette.gov.in",
    "nfra_orders": "https://nfra.gov.in/orders",
    "sebi_circulars": "https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&smid=0&ssid=0",
}


class GovSyncEngine:
    def __init__(self, client: Optional[GovHttpClient] = None, explainer: Optional[GovAiExplainer] = None):
        self.client = client or GovHttpClient()
        self.explainer = explainer or GovAiExplainer()

    def sync_source(self, db: Session, source_code: str, backfilled: bool = False, fetch_pdfs: bool = True) -> Dict[str, Any]:
        """
        Synchronizes a single source. Isolated from other sources.
        """
        source = db.query(GovSource).filter(GovSource.code == source_code).first()
        if not source:
            return {"error": f"Source {source_code} not found in registry", "status": "failed"}

        now = datetime.now(timezone.utc)

        # R6 Check: if blocked_requires_verification, check 24h cool down
        if source.status == "blocked_requires_verification":
            if source.last_run_at and (now - source.last_run_at).total_seconds() < 86400:
                logger.info(f"Source {source.code} is blocked_requires_verification. Skipping within 24h cooldown.")
                return {
                    "source": source.code,
                    "status": "blocked",
                    "reason": "Source requires manual verification after WAF/bot challenge. 24h cooldown active.",
                    "items_new": 0,
                    "items_updated": 0,
                    "items_skipped": 0,
                }

        if not source.enabled:
            logger.info(f"Source {source.code} is disabled. Skipping.")
            return {
                "source": source.code,
                "status": "disabled",
                "items_new": 0,
                "items_updated": 0,
                "items_skipped": 0,
            }

        # Start Fetch Run audit record
        fetch_run = GovFetchRun(
            source_id=source.id,
            started_at=now,
            status="running",
        )
        db.add(fetch_run)
        db.commit()

        source.last_run_at = now
        target_url = SOURCE_FETCH_ENDPOINTS.get(source.code, source.base_url)

        try:
            allowlisted_domains = {source.domain, "www." + source.domain}
            result = self.client.fetch(target_url, allowlisted_domains=allowlisted_domains)

            fetch_run.http_status = result.status_code

            # Check if blocked by WAF/CAPTCHA (R6)
            if result.blocked:
                source.status = "blocked_requires_verification"
                source.captcha_detected = True
                source.last_error = result.block_reason
                fetch_run.status = "blocked"
                fetch_run.error_message = result.block_reason
                fetch_run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    "source": source.code,
                    "status": "blocked",
                    "error": result.block_reason,
                    "items_new": 0,
                    "items_updated": 0,
                    "items_skipped": 0,
                }

            if not result.is_success and not result.not_modified:
                err_msg = result.error or f"HTTP {result.status_code}"
                source.last_error = err_msg
                fetch_run.status = "failed"
                fetch_run.error_message = err_msg
                fetch_run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    "source": source.code,
                    "status": "failed",
                    "error": err_msg,
                    "items_new": 0,
                    "items_updated": 0,
                    "items_skipped": 0,
                }

            # 304 Not Modified
            if result.not_modified:
                source.last_success_at = datetime.now(timezone.utc)
                fetch_run.status = "success"
                fetch_run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    "source": source.code,
                    "status": "success",
                    "items_new": 0,
                    "items_updated": 0,
                    "items_skipped": 0,
                    "note": "304 Not Modified",
                }

            # Parse with appropriate adapter
            raw_items = []
            if source.method == "rss":
                raw_items = RssAdapter.parse(result.text, source.code)
            else:
                raw_items = HtmlListingAdapter.parse(source.code, result.text, source.base_url)

            items_new = 0
            items_updated = 0
            items_skipped = 0

            for raw in raw_items:
                # If item has PDF URL and needs text extraction, fetch first page
                if fetch_pdfs and raw.pdf_url and raw.text_status == "no_text":
                    try:
                        pdf_res = self.client.fetch(raw.pdf_url, allowlisted_domains=allowlisted_domains)
                        if pdf_res.is_success and pdf_res.content:
                            extracted_txt, txt_stat = extract_pdf_text(pdf_res.content, max_pages=10)
                            raw.content_text = extracted_txt if extracted_txt else raw.title
                            raw.text_status = txt_stat
                    except Exception as e:
                        logger.warning(f"Could not extract PDF {raw.pdf_url}: {e}")

                # Normalize attributes
                norm = GovNormalizer.normalize_item(raw, source.code)

                # Deduplication query: by (source_id, doc_number, issue_date) or by url
                existing = None
                if norm["doc_number"] and norm["issue_date"]:
                    existing = (
                        db.query(GovUpdate)
                        .filter(
                            GovUpdate.source_id == source.id,
                            GovUpdate.doc_number == norm["doc_number"],
                            GovUpdate.issue_date == norm["issue_date"],
                        )
                        .first()
                    )

                if not existing:
                    existing = db.query(GovUpdate).filter(GovUpdate.source_id == source.id, GovUpdate.url == norm["url"]).first()

                if existing:
                    if existing.content_hash == norm["content_hash"]:
                        existing.last_seen_at = datetime.now(timezone.utc)
                        items_skipped += 1
                    else:
                        # Content changed: update row in place
                        existing.title = norm["title"]
                        existing.content_text = norm["content_text"]
                        existing.text_status = norm["text_status"]
                        existing.content_hash = norm["content_hash"]
                        existing.category = norm["category"]
                        existing.topics = norm["topics"]
                        existing.doc_type = norm["doc_type"]
                        existing.legal_status = norm["legal_status"]
                        existing.law_version = norm["law_version"]
                        existing.status = norm["status"]
                        existing.status_confidence = norm["status_confidence"]
                        existing.supersedes_refs = norm["supersedes_refs"]
                        existing.updated_at = datetime.now(timezone.utc)
                        existing.last_seen_at = datetime.now(timezone.utc)

                        # Re-run AI explanation if text available
                        if norm["text_status"] == "ok":
                            ai_data, ai_stat = self.explainer.generate_explanation(norm["title"], norm["content_text"], norm["text_status"])
                            existing.ai_summary = ai_data
                            existing.ai_status = ai_stat
                            existing.ai_generated_at = datetime.now(timezone.utc)

                        items_updated += 1
                else:
                    # New item
                    ai_data = None
                    ai_stat = None
                    if norm["text_status"] == "ok":
                        ai_data, ai_stat = self.explainer.generate_explanation(norm["title"], norm["content_text"], norm["text_status"])

                    new_update = GovUpdate(
                        source_id=source.id,
                        title=norm["title"],
                        doc_type=norm["doc_type"],
                        legal_status=norm["legal_status"],
                        doc_number=norm["doc_number"],
                        issue_date=norm["issue_date"],
                        effective_date=norm["effective_date"],
                        category=norm["category"],
                        topics=norm["topics"],
                        law_version=norm["law_version"],
                        url=norm["url"],
                        pdf_url=norm["pdf_url"],
                        content_text=norm["content_text"],
                        text_status=norm["text_status"],
                        content_hash=norm["content_hash"],
                        status=norm["status"],
                        status_confidence=norm["status_confidence"],
                        supersedes_refs=norm["supersedes_refs"],
                        first_seen_at=datetime.now(timezone.utc),
                        last_seen_at=datetime.now(timezone.utc),
                        fetched_at=datetime.now(timezone.utc),
                        updated_at=datetime.now(timezone.utc),
                        backfilled=backfilled,
                        ai_summary=ai_data,
                        ai_model=self.explainer.settings.GEMINI_MODEL if ai_data else None,
                        ai_generated_at=datetime.now(timezone.utc) if ai_data else None,
                        ai_status=ai_stat,
                    )
                    db.add(new_update)
                    items_new += 1

            # Update Source & Fetch Run
            finish_time = datetime.now(timezone.utc)
            source.status = "ok"
            source.last_success_at = finish_time
            source.last_error = None

            fetch_run.status = "success"
            fetch_run.items_new = items_new
            fetch_run.items_updated = items_updated
            fetch_run.items_skipped = items_skipped
            fetch_run.finished_at = finish_time

            db.commit()

            return {
                "source": source.code,
                "status": "success",
                "items_new": items_new,
                "items_updated": items_updated,
                "items_skipped": items_skipped,
            }

        except Exception as e:
            logger.error(f"Error syncing source {source.code}: {e}", exc_info=True)
            db.rollback()
            source.last_error = str(e)
            fetch_run.status = "failed"
            fetch_run.error_message = str(e)
            fetch_run.finished_at = datetime.now(timezone.utc)
            db.commit()
            return {
                "source": source.code,
                "status": "failed",
                "error": str(e),
                "items_new": 0,
                "items_updated": 0,
                "items_skipped": 0,
            }

    def sync_all(self, db: Session, backfilled: bool = False) -> List[Dict[str, Any]]:
        """
        Synchronizes all enabled sources sequentially with isolation.
        """
        enabled_sources = db.query(GovSource).filter(GovSource.enabled == True).all()
        results = []
        for s in enabled_sources:
            try:
                res = self.sync_source(db, s.code, backfilled=backfilled)
                results.append(res)
            except Exception as e:
                logger.error(f"Top-level failure on {s.code}: {e}")
                results.append({"source": s.code, "status": "failed", "error": str(e)})
        return results
