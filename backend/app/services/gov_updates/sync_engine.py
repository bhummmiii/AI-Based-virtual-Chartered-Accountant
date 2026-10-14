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
from app.services.gov_updates.status_manager import record_source_attempt, is_source_fetchable

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
        Enforces K1: Blocked/unreachable/disabled or cooldown sources are never fetched.
        """
        source = db.query(GovSource).filter(GovSource.code == source_code).first()
        if not source:
            return {"error": f"Source {source_code} not found in registry", "status": "failed"}

        now = datetime.now(timezone.utc)

        # K1 Enforcement: check eligibility and cooldown
        if not is_source_fetchable(source, now):
            logger.info(f"Source {source.code} not eligible for fetch (status={source.status}, next_retry={source.next_retry_at}, enabled={source.enabled}).")
            return {
                "source": source.code,
                "status": source.status,
                "skipped": True,
                "reason": f"Source {source.code} is {source.status} (enabled={source.enabled}) and in cooldown until {source.next_retry_at}.",
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

        target_url = SOURCE_FETCH_ENDPOINTS.get(source.code, source.base_url)

        try:
            allowlisted_domains = {source.domain, "www." + source.domain}
            result = self.client.fetch(target_url, allowlisted_domains=allowlisted_domains)

            fetch_run.http_status = result.status_code

            # Check if blocked by WAF/CAPTCHA (R6)
            if result.blocked:
                record_source_attempt(
                    source=source,
                    success=False,
                    now=datetime.now(timezone.utc),
                    failure_stage="http_challenge",
                    error_message=result.block_reason,
                    is_blocked=True,
                )
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
                f_stage = "tcp" if "timeout" in err_msg.lower() else "network"
                record_source_attempt(
                    source=source,
                    success=False,
                    now=datetime.now(timezone.utc),
                    failure_stage=f_stage,
                    error_message=err_msg,
                )
                fetch_run.status = "failed"
                fetch_run.error_message = err_msg
                fetch_run.finished_at = datetime.now(timezone.utc)
                db.commit()
                return {
                    "source": source.code,
                    "status": source.status,
                    "error": err_msg,
                    "items_new": 0,
                    "items_updated": 0,
                    "items_skipped": 0,
                }

            # 304 Not Modified
            if result.not_modified:
                record_source_attempt(source=source, success=True, now=datetime.now(timezone.utc))
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
            record_source_attempt(source=source, success=True, now=finish_time, items_count=items_new)

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
            record_source_attempt(
                source=source,
                success=False,
                now=datetime.now(timezone.utc),
                failure_stage="exception",
                error_message=str(e),
            )
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
        Synchronizes all eligible sources sequentially with isolation per K1.
        Only fetches enabled sources whose status is ok or degraded and past cool-down.
        """
        now = datetime.now(timezone.utc)
        fetchable_sources = [s for s in db.query(GovSource).all() if is_source_fetchable(s, now)]
        results = []
        for s in fetchable_sources:
            try:
                res = self.sync_source(db, s.code, backfilled=backfilled)
                results.append(res)
            except Exception as e:
                logger.error(f"Top-level failure on {s.code}: {e}")
                results.append({"source": s.code, "status": "failed", "error": str(e)})
        return results
