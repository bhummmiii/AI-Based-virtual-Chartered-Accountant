"""
GovUpdateService — Business logic for querying, filtering, saving, and syncing government updates.
"""

import uuid
from datetime import datetime, timezone, timedelta, date
from typing import Optional, List, Dict, Any
from sqlalchemy import func, or_, and_, desc
from sqlalchemy.orm import Session

from app.models.government_update import GovSource, GovUpdate, GovSavedUpdate, GovFetchRun
from app.models.user import User
from app.schemas.government_update import (
    GovUpdateResponse,
    GovUpdatesListResponse,
    GovMetaResponse,
    GovSourceResponse,
)
from app.services.gov_updates.sync_engine import GovSyncEngine


class GovUpdateService:
    @classmethod
    def list_updates(
        cls,
        db: Session,
        user: User,
        category: Optional[str] = None,
        source_code: Optional[str] = None,
        doc_type: Optional[str] = None,
        law_version: Optional[str] = None,
        topic: Optional[str] = None,
        status: Optional[str] = None,
        legal_status: Optional[str] = None,
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
        q: Optional[str] = None,
        saved_only: bool = False,
        include_archive: bool = True,
        show_administrative: bool = False,
        show_hidden: bool = False,
        page: int = 1,
        page_size: int = 20,
    ) -> GovUpdatesListResponse:
        query = db.query(GovUpdate).join(GovSource)

        # Hidden & Administrative filtering (K5 & K12)
        if not show_hidden:
            if show_administrative:
                query = query.filter(
                    or_(
                        GovUpdate.hidden == False,
                        GovUpdate.legal_status.in_(["administrative_not_law", "newsletter"])
                    )
                )
            else:
                query = query.filter(GovUpdate.hidden == False)
                query = query.filter(GovUpdate.legal_status != "administrative_not_law")

        # Filters
        if category and category.upper() != "ALL":
            cat_upper = category.upper()
            if cat_upper == "INCOME_TAX":
                query = query.filter(GovUpdate.category.in_(["INCOME_TAX", "TDS"]))
            else:
                query = query.filter(GovUpdate.category == cat_upper)

        if source_code:
            query = query.filter(GovSource.code == source_code)

        if doc_type:
            query = query.filter(GovUpdate.doc_type == doc_type.lower())

        if law_version:
            query = query.filter(GovUpdate.law_version == law_version)

        if topic:
            # Check topic in JSON array
            query = query.filter(GovUpdate.topics.contains([topic]))

        if status:
            query = query.filter(GovUpdate.status == status.lower())
        elif not include_archive:
            query = query.filter(GovUpdate.status == "active")

        if legal_status:
            query = query.filter(GovUpdate.legal_status == legal_status.lower())

        if date_from:
            query = query.filter(GovUpdate.issue_date >= date_from)

        if date_to:
            query = query.filter(GovUpdate.issue_date <= date_to)

        if q:
            search_term = f"%{q.strip()}%"
            query = query.filter(
                or_(
                    GovUpdate.title.ilike(search_term),
                    GovUpdate.content_text.ilike(search_term),
                    GovUpdate.doc_number.ilike(search_term),
                )
            )

        # Saved only filter
        saved_ids_query = db.query(GovSavedUpdate.update_id).filter(GovSavedUpdate.user_id == user.id)
        saved_ids_set = {row[0] for row in saved_ids_query.all()}

        if saved_only:
            query = query.filter(GovUpdate.id.in_(saved_ids_set))

        # Total count before pagination
        total = query.count()

        # Sorting: issue_date desc then first_seen_at desc
        query = query.order_by(
            GovUpdate.issue_date.desc().nullslast(),
            GovUpdate.first_seen_at.desc(),
        )

        # Pagination
        offset = (page - 1) * page_size
        updates = query.offset(offset).limit(page_size).all()

        now_dt = datetime.now(timezone.utc)
        cutoff_14d_dt = now_dt - timedelta(days=14)
        cutoff_14d_date = now_dt.date() - timedelta(days=14)

        # K8 Rule: New = issue_date known AND issue_date within 14d AND first_seen_at within 14d AND not backfilled
        def check_is_new(issue_dt: Optional[date], seen_dt: Optional[datetime], backfilled: bool) -> bool:
            if not issue_dt or not seen_dt or backfilled:
                return False
            if issue_dt < cutoff_14d_date:
                return False
            if seen_dt.tzinfo is None:
                seen_dt = seen_dt.replace(tzinfo=timezone.utc)
            return seen_dt >= cutoff_14d_dt

        items_res: List[GovUpdateResponse] = []
        for u in updates:
            is_new = check_is_new(u.issue_date, u.first_seen_at, bool(u.backfilled))
            is_saved = u.id in saved_ids_set

            items_res.append(
                GovUpdateResponse(
                    id=u.id,
                    source_id=u.source_id,
                    source_name=u.source.name if u.source else None,
                    source_code=u.source.code if u.source else None,
                    source_domain=u.source.domain if u.source else None,
                    title=u.title,
                    doc_type=u.doc_type,
                    legal_status=u.legal_status,
                    doc_number=u.doc_number,
                    doc_number_source=u.doc_number_source,
                    issue_date=u.issue_date,
                    issue_date_source=u.issue_date_source,
                    date_precision=u.date_precision or "day",
                    effective_date=u.effective_date,
                    category=u.category,
                    topics=u.topics or [],
                    law_version=u.law_version,
                    url=u.url,
                    link_quality=u.link_quality or "direct_document",
                    ministry=u.ministry,
                    pdf_url=u.pdf_url,
                    content_text=u.content_text,
                    text_status=u.text_status,
                    status=u.status,
                    status_confidence=u.status_confidence,
                    supersedes_refs=u.supersedes_refs or [],
                    hidden=bool(u.hidden),
                    hidden_reason=u.hidden_reason,
                    is_manual=bool(u.is_manual),
                    manual_added_at=u.manual_added_at,
                    first_seen_at=u.first_seen_at,
                    fetched_at=u.fetched_at,
                    updated_at=u.updated_at,
                    backfilled=u.backfilled,
                    is_new=is_new,
                    is_saved=is_saved,
                    ai_summary=u.ai_summary,
                    ai_status=u.ai_status,
                )
            )

        # Facets computation across all active items
        cat_counts = dict(
            db.query(GovUpdate.category, func.count(GovUpdate.id))
            .group_by(GovUpdate.category)
            .all()
        )
        type_counts = dict(
            db.query(GovUpdate.doc_type, func.count(GovUpdate.id))
            .group_by(GovUpdate.doc_type)
            .all()
        )
        law_counts = dict(
            db.query(GovUpdate.law_version, func.count(GovUpdate.id))
            .group_by(GovUpdate.law_version)
            .all()
        )
        status_counts = dict(
            db.query(GovUpdate.status, func.count(GovUpdate.id))
            .group_by(GovUpdate.status)
            .all()
        )

        facets = {
            "categories": cat_counts,
            "doc_types": type_counts,
            "law_versions": law_counts,
            "statuses": status_counts,
        }

        return GovUpdatesListResponse(
            items=items_res,
            total=total,
            page=page,
            page_size=page_size,
            facets=facets,
        )

    @classmethod
    def get_update_by_id(cls, db: Session, user: User, update_id: uuid.UUID) -> Optional[GovUpdateResponse]:
        u = db.query(GovUpdate).filter(GovUpdate.id == update_id).first()
        if not u:
            return None

        is_saved = (
            db.query(GovSavedUpdate)
            .filter(GovSavedUpdate.user_id == user.id, GovSavedUpdate.update_id == u.id)
            .first()
            is not None
        )
        now_dt = datetime.now(timezone.utc)
        cutoff_14d_dt = now_dt - timedelta(days=14)
        cutoff_14d_date = now_dt.date() - timedelta(days=14)

        is_new = False
        if u.issue_date and u.first_seen_at and not u.backfilled and u.issue_date >= cutoff_14d_date:
            seen_dt = u.first_seen_at
            if seen_dt.tzinfo is None:
                seen_dt = seen_dt.replace(tzinfo=timezone.utc)
            is_new = seen_dt >= cutoff_14d_dt

        return GovUpdateResponse(
            id=u.id,
            source_id=u.source_id,
            source_name=u.source.name if u.source else None,
            source_code=u.source.code if u.source else None,
            source_domain=u.source.domain if u.source else None,
            title=u.title,
            doc_type=u.doc_type,
            legal_status=u.legal_status,
            doc_number=u.doc_number,
            doc_number_source=u.doc_number_source,
            issue_date=u.issue_date,
            issue_date_source=u.issue_date_source,
            date_precision=u.date_precision or "day",
            effective_date=u.effective_date,
            category=u.category,
            topics=u.topics or [],
            law_version=u.law_version,
            url=u.url,
            link_quality=u.link_quality or "direct_document",
            ministry=u.ministry,
            pdf_url=u.pdf_url,
            content_text=u.content_text,
            text_status=u.text_status,
            status=u.status,
            status_confidence=u.status_confidence,
            supersedes_refs=u.supersedes_refs or [],
            hidden=bool(u.hidden),
            hidden_reason=u.hidden_reason,
            is_manual=bool(u.is_manual),
            manual_added_at=u.manual_added_at,
            first_seen_at=u.first_seen_at,
            fetched_at=u.fetched_at,
            updated_at=u.updated_at,
            backfilled=u.backfilled,
            is_new=is_new,
            is_saved=is_saved,
            ai_summary=u.ai_summary,
            ai_status=u.ai_status,
        )

    @classmethod
    def save_update(cls, db: Session, user: User, update_id: uuid.UUID) -> bool:
        u = db.query(GovUpdate).filter(GovUpdate.id == update_id).first()
        if not u:
            return False

        existing = (
            db.query(GovSavedUpdate)
            .filter(GovSavedUpdate.user_id == user.id, GovSavedUpdate.update_id == update_id)
            .first()
        )
        if not existing:
            saved = GovSavedUpdate(user_id=user.id, update_id=update_id)
            db.add(saved)
            db.commit()
        return True

    @classmethod
    def unsave_update(cls, db: Session, user: User, update_id: uuid.UUID) -> bool:
        existing = (
            db.query(GovSavedUpdate)
            .filter(GovSavedUpdate.user_id == user.id, GovSavedUpdate.update_id == update_id)
            .first()
        )
        if existing:
            db.delete(existing)
            db.commit()
        return True

    @classmethod
    def get_meta(cls, db: Session) -> GovMetaResponse:
        from app.schemas.government_update import GovCategorySourceItem

        cat_counts = dict(
            db.query(GovUpdate.category, func.count(GovUpdate.id))
            .filter(GovUpdate.hidden == False)
            .group_by(GovUpdate.category)
            .all()
        )
        total_updates = db.query(GovUpdate).filter(GovUpdate.hidden == False).count()

        sources = db.query(GovSource).all()
        total_sources = len(sources)
        sources_ok = sum(1 for s in sources if s.status == "ok")
        sources_degraded = sum(1 for s in sources if s.status == "degraded")
        sources_blocked = sum(1 for s in sources if s.status == "blocked_requires_verification")
        sources_unreachable = sum(1 for s in sources if s.status == "unreachable")
        sources_disabled = sum(1 for s in sources if s.status == "disabled")

        last_sync = max((s.last_success_at for s in sources if s.last_success_at), default=None)
        last_attempt = max((s.last_attempt_at for s in sources if s.last_attempt_at), default=None)

        CATEGORY_SOURCE_MAPPING = {
            "GST": ["gstcouncil", "cbic_gst", "cbic_taxinfo", "gstn_news", "mahagst", "icai_idtc", "gstat"],
            "INCOME_TAX": ["incometax_feed", "dor", "incometax_press_rss"],
            "BUDGET": ["indiabudget", "finmin", "dor"],
            "ACCOUNTING": ["icai_announcements", "nfra_orders", "icai_accounting_std"],
            "BANKING": ["rbi_notifications", "rbi_pressreleases"],
            "CORPORATE_LAW": ["mca", "sebi_circulars"],
        }
        source_by_code = {s.code: s for s in sources}
        category_sources_map = {}
        for cat, codes in CATEGORY_SOURCE_MAPPING.items():
            cat_list = []
            for c in codes:
                if c in source_by_code:
                    src_obj = source_by_code[c]
                    cat_list.append(GovCategorySourceItem(
                        code=src_obj.code,
                        name=src_obj.name,
                        status=src_obj.status,
                        enabled=src_obj.enabled,
                        last_error=src_obj.last_error if src_obj.status != "ok" else None,
                    ))
            category_sources_map[cat] = cat_list

        return GovMetaResponse(
            category_counts=cat_counts,
            total_updates=total_updates,
            last_sync_at=last_sync,
            last_attempt_at=last_attempt,
            sources_total=total_sources,
            sources_ok=sources_ok,
            sources_degraded=sources_degraded,
            sources_blocked=sources_blocked,
            sources_unreachable=sources_unreachable,
            sources_disabled=sources_disabled,
            category_sources=category_sources_map,
        )

    @classmethod
    def list_sources(cls, db: Session) -> List[GovSourceResponse]:
        sources = db.query(GovSource).order_by(GovSource.tier, GovSource.name).all()
        return [GovSourceResponse.model_validate(s) for s in sources]

    @classmethod
    def toggle_source(cls, db: Session, source_id: uuid.UUID, enabled: bool) -> Optional[GovSourceResponse]:
        source = db.query(GovSource).filter(GovSource.id == source_id).first()
        if not source:
            return None
        source.enabled = enabled
        source.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(source)
        return GovSourceResponse.model_validate(source)

    @classmethod
    def reprobe_source(cls, db: Session, source_id: uuid.UUID) -> GovSourceResponse:
        from fastapi import HTTPException
        source = db.query(GovSource).filter(GovSource.id == source_id).first()
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")

        now = datetime.now(timezone.utc)
        if source.last_probe_at and (now - source.last_probe_at).total_seconds() < 3600:
            remaining = int((3600 - (now - source.last_probe_at).total_seconds()) / 60)
            raise HTTPException(
                status_code=429,
                detail=f"Re-probe rate-limited. Please wait {remaining} minutes before re-probing {source.name}."
            )

        from scripts.gov_source_diagnose import diagnose_source
        src_dict = {
            "code": source.code,
            "name": source.name,
            "url": source.base_url,
            "base_url": source.base_url,
        }
        diag = diagnose_source(src_dict)

        from app.services.gov_updates.status_manager import record_source_attempt
        source.last_probe_at = now
        if diag["classification"] == "ok":
            record_source_attempt(source, success=True, now=now)
        else:
            record_source_attempt(
                source,
                success=False,
                now=now,
                failure_stage=diag.get("failure_stage"),
                error_message=diag.get("error_detail"),
                is_blocked=diag.get("is_bot_blocked", False),
            )
        db.commit()
        db.refresh(source)
        return GovSourceResponse.model_validate(source)

    @classmethod
    def trigger_sync(
        cls,
        db: Session,
        source_code: Optional[str] = None,
        backfill: bool = False,
    ) -> Dict[str, Any]:
        engine = GovSyncEngine()
        if source_code:
            return engine.sync_source(db, source_code, backfilled=backfill)
        else:
            results = engine.sync_all(db, backfilled=backfill)
            return {"results": results, "total_synced": len(results)}

    @classmethod
    def manual_import(
        cls,
        db: Session,
        user: User,
        filename: str,
        file_bytes: bytes,
        official_url: str,
        category: str,
        doc_type: str,
        source_id: Optional[uuid.UUID] = None,
        title: Optional[str] = None,
        doc_number: Optional[str] = None,
        issue_date: Optional[date] = None,
        effective_date: Optional[date] = None,
    ) -> GovUpdateResponse:
        import re
        from fastapi import HTTPException
        from app.services.gov_updates.adapters.pdf_extractor import extract_pdf_text
        from app.services.gov_updates.text_quality import evaluate_and_clean_document_text
        from app.services.gov_updates.adapters.html_adapter import parse_date_strict
        from app.services.gov_updates.normalizer import GovNormalizer, compute_content_hash
        from app.services.gov_updates.ai_explainer import GovAiExplainer

        ALLOWED_OFFICIAL_DOMAINS = [
            ".gov.in",
            ".nic.in",
            "rbi.org.in",
            "icai.org",
            "sebi.gov.in",
            "nfra.gov.in",
            "epfindia.gov.in",
            "esic.gov.in",
        ]
        url_lower = official_url.lower()
        if not any(dom in url_lower for dom in ALLOWED_OFFICIAL_DOMAINS):
            raise HTTPException(
                status_code=400,
                detail="Official URL domain must belong to the official government allowlist (.gov.in, .nic.in, rbi.org.in, icai.org, sebi.gov.in, nfra.gov.in, etc.)",
            )

        if len(file_bytes) > 15 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="Uploaded file exceeds maximum limit of 15 MB.")

        content_text = ""
        text_status = "no_text"
        if filename.lower().endswith(".pdf"):
            content_text, text_status = extract_pdf_text(file_bytes)
        else:
            try:
                raw_txt = file_bytes.decode("utf-8", errors="replace")
                content_text, text_status = evaluate_and_clean_document_text(raw_txt)
            except Exception:
                content_text = ""
                text_status = "no_text"

        final_title = title.strip() if title else ""
        if not final_title:
            if content_text:
                first_line = content_text.strip().split("\n")[0][:200].strip()
                final_title = first_line or filename
            else:
                final_title = filename

        final_issue_date = issue_date
        date_precision = "day" if final_issue_date else "none"
        date_source = "user_input" if final_issue_date else "none"
        if not final_issue_date and content_text:
            parsed_d, prec = parse_date_strict(content_text[:1000])
            if parsed_d:
                final_issue_date = parsed_d
                date_precision = prec
                date_source = "document_text"

        final_doc_num = doc_number.strip() if doc_number else None
        doc_num_source = "user_input" if final_doc_num else None
        if not final_doc_num and content_text:
            circ_m = re.search(r"(?:Circular|Notification|Order)\s+(?:No\.?|Number)?\s*([A-Za-z0-9\-/]+)", content_text[:1000], re.IGNORECASE)
            if circ_m:
                final_doc_num = circ_m.group(1).strip()
                doc_num_source = "document_text"

        target_source = None
        if source_id:
            target_source = db.query(GovSource).filter(GovSource.id == source_id).first()
        if not target_source:
            target_source = db.query(GovSource).first()

        content_hash = compute_content_hash(final_title, content_text, final_doc_num, final_issue_date)

        existing = db.query(GovUpdate).filter(GovUpdate.content_hash == content_hash).first()
        if not existing and final_doc_num and final_issue_date:
            existing = db.query(GovUpdate).filter(
                GovUpdate.doc_number == final_doc_num,
                GovUpdate.issue_date == final_issue_date,
            ).first()

        if existing:
            # Second import of the same file creates no duplicate
            return cls.get_update_by_id(db, user, existing.id)

        source_code = target_source.code if target_source else ""
        norm_cat = category or GovNormalizer.classify_category(source_code, final_title, content_text)
        norm_type = doc_type or GovNormalizer.classify_doc_type(final_title, official_url, content_text)
        leg_status = GovNormalizer.classify_legal_status(norm_type, final_title, content_text, source_code=source_code, category=norm_cat)
        law_ver = GovNormalizer.detect_law_version(final_title, content_text)
        topics = GovNormalizer.extract_topics(final_title, content_text)
        status, confidence, supersedes_refs = GovNormalizer.detect_supersedes(final_title, content_text)

        ai_summary = None
        ai_status = "none"
        if text_status == "ok":
            explainer = GovAiExplainer()
            ai_summary, ai_status = explainer.generate_explanation(final_title, content_text, text_status)

        now = datetime.now(timezone.utc)
        new_u = GovUpdate(
            source_id=target_source.id,
            title=final_title,
            doc_type=norm_type,
            legal_status=leg_status,
            doc_number=final_doc_num,
            doc_number_source=doc_num_source,
            issue_date=final_issue_date,
            issue_date_source=date_source,
            date_precision=date_precision,
            effective_date=effective_date,
            category=norm_cat,
            topics=topics,
            law_version=law_ver,
            url=official_url.strip(),
            link_quality="direct_document",
            content_text=content_text,
            text_status=text_status,
            content_hash=content_hash,
            status=status,
            status_confidence=confidence,
            supersedes_refs=supersedes_refs,
            hidden=False,
            is_manual=True,
            manual_added_by=user.id,
            manual_added_at=now,
            first_seen_at=now,
            last_seen_at=now,
            fetched_at=now,
            updated_at=now,
            backfilled=False,
            ai_summary=ai_summary,
            ai_status=ai_status,
        )
        db.add(new_u)

        run = GovFetchRun(
            source_id=target_source.id,
            started_at=now,
            finished_at=now,
            status="success",
            items_new=1,
            error_message=f"Manual circular upload by CA/Admin {user.id} ({filename})",
        )
        db.add(run)
        db.commit()
        db.refresh(new_u)

        return cls.get_update_by_id(db, user, new_u.id)
