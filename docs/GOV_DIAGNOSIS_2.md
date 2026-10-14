# FinLedger AI — Government Updates Phase A Diagnosis (`docs/GOV_DIAGNOSIS_2.md`)

**Date of Diagnosis:** 2026-10-14  
**Auditor / Engineer:** Senior Full-Stack Engineer  
**Live Stack Environment:** Python 3.14.5 / FastAPI / PostgreSQL 18 / Windows  
**Status:** COMPLETE (Zero Data Modifications in Phase A)

---

## 1. Executive Summary & Core Findings

This document records the stage-wise empirical diagnosis across all registered government update sources and candidate statutory endpoints, as well as an exhaustive data audit of the current `gov_updates` database table.

### Key Takeaways:
1. **Source Status Truth vs UI Display (P1 & A4 Root Cause):**
   - The UI previously displayed sources like `cbic_taxinfo`, `gstn_news`, `incometax_feed`, `pib_rss`, `finmin`, and `mahagst` with an **"OK"** badge alongside red error text.
   - **Root Cause:** In `sync_engine.py` (lines 112–117), when an HTTP request failed (e.g. TCP timeout or 403), `source.last_error` was updated, but `source.status` was **never** updated to `unreachable` or `degraded`. It remained `status = "ok"` as initialized in the seed!
   - Furthermore, the sync engine lacked transitions to `unreachable` or `degraded`, and `egazette_recent` was mistakenly set to `enabled = False` in the database, even though its items were displayed.
2. **Real Endpoint Probing (P2 & A2 Findings):**
   - Direct RSS feeds for Income Tax (`/press-release-rss-feed/-/asset_publisher/ovrx/rss`, `/notifications-rss-feed/...`, `/circulars-rss-feed/...`) and PIB (`/rss/RssMain.aspx?ModId=1` & `ModId=2`) were probed with stage-wise granularity.
   - Both `incometaxindia.gov.in` and `pib.gov.in` return **HTTP 403 WAF Challenge** even for default baseline clients without custom user agents. These sites have perimeter bot protection (Cloudflare / Akamai / NIC Gateway ASM) preventing automated scraping from external IP addresses. Per Hard Rule **R6**, these sources **must remain blocked/unreachable without attempting WAF bypass or CAPTCHA solving**. The legitimate path for these documents is the manual upload feature (**K10**).
   - High-value working statutory endpoints found: **ICAI Indirect Taxes Committee** (`idtc.icai.org`, HTTP 200, GST updates), **GST Appellate Tribunal** (`gstat.gov.in`, HTTP 200), **Department of Revenue** (`dor.gov.in`, HTTP 200).
3. **Data Quality Audit (P3, P4, P5, P6, P7, P8 & A3 Findings):**
   - **Dates Guessed (P3):** 19 rows carry artificial `day = 01` dates derived from URL directory segments (e.g. `/2026-10/` -> `2026-10-01` instead of the official listing date `2026-10-08` for the 57th GST Council meeting).
   - **Synthetic Numbers (P4):** 53 rows contain synthetic/untraced document numbers (such as `#GSTC-57TH`, `#GSTC-56TH`, and ICAI slug numbers).
   - **Administrative Mislabeled (P5):** 4 rows are vacancies/appointments for consultants/members tagged as `operative_instrument`.
   - **e-Gazette Noise (P6):** All 4 e-Gazette rows currently in the DB belong to Ministry of Railways (3) and Ministry of Defence (1), with 0 tax/accounting relevance.
   - **Garbled Text (P7):** 11 rows suffer from severe quality issues, notably the *81st Edition GSTC Newsletter December 2025* with a 90% letter-spaced token ratio (`M E S S A G E   T h e   F i f t h...`).
   - **False "New" Badges (P8):** 24 rows older than 14 days have `backfilled = false`, causing them to show "New" badges.

---

## 2. Stage-Wise Diagnostic Table (A1 & A2)

Stage breakdown executed across 3 consecutive iterations (spaced 60s apart) from the live backend server.
- **Stages:** DNS Resolution -> TCP Connect (10s timeout) -> TLS Handshake -> GET `/robots.txt` -> GET Target Path (20s timeout, max 15MB).
- **Classification:** `ok` | `degraded` | `blocked_requires_verification` | `unreachable` | `disabled`.

| Source Code | Domain / Host | IPs | DNS | TCP | TLS | robots.txt | HTTP | Failure Stage | Classification | Bot-Block vs Network/Site |
|---|---|---|---|---|---|---|---|---|---|---|
| `rbi_notifications` | `rbi.org.in` | 104.18.32.7 | OK | OK | OK | OK | 200 | None | `ok` | Operational |
| `rbi_pressreleases` | `rbi.org.in` | 104.18.32.7 | OK | OK | OK | OK | 200 | None | `ok` | Operational |
| `gstcouncil` | `gstcouncil.gov.in` | 164.100.154.51 | OK | OK | OK | OK | 200 | None | `ok` | Operational |
| `icai_announcements`| `www.icai.org` | 104.18.22.148 | OK | OK | OK | OK | 200 | None | `ok` | Operational |
| `egazette_recent` | `egazette.gov.in` | 164.100.128.21 | OK | OK | OK | OK | 200 | None | `ok` (listing-only) | Operational |
| `nfra_orders` | `nfra.gov.in` | 164.100.154.72 | OK | OK | OK | OK | 200 | None | `ok` | Operational |
| `sebi_circulars` | `www.sebi.gov.in` | 104.18.18.42 | OK | OK | OK | OK | 200 | None | `ok` | Operational |
| `cbic_taxinfo` | `taxinformation.cbic.gov.in` | 163.227.109.58 | OK | OK | OK | OK | 200 | parser | `degraded` | SPA without static listing links |
| `cbic_gst` | `cbic-gst.gov.in` | 163.227.109.192 | OK | OK | Failed | Error | None | tls | `unreachable` | SSL Handshake failure on NIC server |
| `gstn_news` | `www.gst.gov.in` | 104.18.25.120 | OK | OK | OK | OK | 403 | http_challenge | `blocked_requires_verification` | Cloudflare/WAF Bot Block |
| `incometax_feed` | `incometaxindia.gov.in` | 104.18.37.112 | OK | OK | OK | 403 | 403 | http_challenge | `blocked_requires_verification` | Akamai/WAF Block (baseline also 403) |
| `pib_rss` | `pib.gov.in` | 164.100.154.34 | OK | OK | OK | OK | 403 | http_challenge | `blocked_requires_verification` | NIC ASM/WAF Block on /RssMain.aspx |
| `mca` | `www.mca.gov.in` | 104.18.20.91 | OK | OK | OK | 403 | 403 | http_challenge | `blocked_requires_verification` | Cloudflare WAF Challenge |
| `finmin` | `finmin.gov.in` | 164.100.154.21 | OK | Timeout | N/A | N/A | None | tcp | `unreachable` | NIC Gateway TCP 443 Drop |
| `dor` | `dor.gov.in` | 164.100.154.24 | OK | OK | OK | OK | 200 | None | `ok` | Operational |
| `indiabudget` | `www.indiabudget.gov.in` | 104.18.21.84 | OK | OK | OK | OK | 403 | http_challenge | `blocked_requires_verification` | Cloudflare WAF Challenge |
| `mahagst` | `mahagst.gov.in` | 115.124.103.85 | OK | OK | OK | OK | 200 | None | `degraded` | Redirects to ASPX portal |

### Candidate Endpoints Probe (A2 & K11):
| Endpoint Code | Target URL | HTTP Code | Classification | Notes |
|---|---|---|---|---|
| `incometax_press_rss` | `incometaxindia.gov.in/press-release-rss-feed/...` | 403 | `blocked_requires_verification` | Direct RSS feed blocked by Akamai WAF |
| `incometax_notif_rss` | `incometaxindia.gov.in/notifications-rss-feed/...` | 403 | `blocked_requires_verification` | Direct RSS feed blocked by Akamai WAF |
| `incometax_circ_rss` | `incometaxindia.gov.in/circulars-rss-feed/...` | 403 | `blocked_requires_verification` | Direct RSS feed blocked by Akamai WAF |
| `pib_mof_rss` | `pib.gov.in/rss/RssMain.aspx?ModId=1` | 403 | `blocked_requires_verification` | MoF feed blocked by NIC ASM WAF |
| `pib_mca_rss` | `pib.gov.in/rss/RssMain.aspx?ModId=2` | 403 | `blocked_requires_verification` | MCA feed blocked by NIC ASM WAF |
| `icai_idtc` | `https://idtc.icai.org` | 200 | `ok` | **Working!** Direct GST updates and circulars |
| `gstat` | `https://gstat.gov.in` | 200 | `ok` | **Working!** GST Appellate Tribunal orders |
| `dggi` | `https://dggi.gov.in` | None | `unreachable` | TCP connection timed out |
| `indiacode` | `https://www.indiacode.nic.in` | 403 | `blocked_requires_verification` | NIC WAF block |
| `epfo` | `https://www.epfindia.gov.in` | 200 | `ok` | Working (optional source) |
| `esic` | `https://www.esic.gov.in` | 200 | `ok` | Working (optional source) |

---

## 3. Database Data Audit (A3)

Audited `gov_updates` table (75 total records in live database):

### 3.1. Row Counts by Source
- `rbi_pressreleases`: 22 rows
- `gstcouncil`: 20 rows
- `icai_announcements`: 17 rows
- `rbi_notifications`: 11 rows
- `egazette_recent`: 4 rows
- `nfra_orders`: 1 row
- All other 11 sources: 0 rows

### 3.2. Distribution by Document Type & Legal Status
- **doc_type:** `other` (27), `press_release` (24), `notification` (13), `circular` (4), `act` (2), `gazette` (2), `faq` (2), `order` (1).
- **legal_status:** `press_release_not_law` (25), `unknown` (24), `operative_instrument` (22), `draft_or_proposal` (3), `advisory` (1).

### 3.3. Specific Defect Counts
1. **Guessed Day 01 Dates (P3):** **19 rows**
   - E.g. `2026-10-01` for "Recommendations of the 57th Meeting of the GST Council" (official date is `2026-10-08`).
   - E.g. `2025-09-01` for "Recommendations of the 56th Meeting of the GST Council" (official date is `2025-09-03`).
2. **Synthesized / Untraced Document Numbers (P4):** **53 rows**
   - Includes `#GSTC-57TH`, `#GSTC-56TH`, and fabricated ICAI slug identifiers (`ICAI-convocation-sep-2026`, `ICAI-exam-spmt-24082026`).
3. **Mislabeled Administrative Items (P5):** **4 rows**
   - Items with keywords `vacancy`, `consultant`, `appointment of` improperly tagged `operative_instrument`.
4. **e-Gazette Irrelevant Ministries (P6):** **4 rows**
   - Ministry of Railways: 3 rows
   - Ministry of Defence: 1 row
   - Allowlisted tax ministries: 0 rows
5. **Garbled / Letter-Spaced Text (P7):** **11 rows**
   - `81st Edition GSTC Newsletter December 2025` has a letter-spaced ratio of 90% (`M E S S A G E   T h e   F i f t h...`).
6. **Outdated Items Marked "New" (P8):** **24 rows**
   - Items with issue dates in 2024, 2025, or early 2026 incorrectly flagged `is_new = true` because they were first synced on 2026-10-12 without `backfilled = true`.

---

## 4. Root Cause Analysis: Registry Status & Header Display (A4)

1. **Why Blocked / Unreachable Sources Showed "OK" with Red Error Text:**
   - In `backend/app/services/gov_updates/sync_engine.py` (lines 112–117):
     ```python
     if not result.is_success and not result.not_modified:
         err_msg = result.error or f"HTTP {result.status_code}"
         source.last_error = err_msg
         fetch_run.status = "failed"
         # BUG: source.status was never updated! It stayed "ok" from the seed!
     ```
   - In `backend/app/services/gov_updates/service.py` (`toggle_source`):
     ```python
     if not enabled:
         source.status = "disabled"
     elif source.status == "disabled":
         source.status = "ok" # BUG: Restoring an enabled source forced it to "ok", erasing its blocked/unreachable state!
     ```
2. **Why the Header Count was Inaccurate:**
   - The header only computed `meta.sources_total` and `meta.sources_blocked`, completely omitting `degraded`, `unreachable`, and `disabled` states.
   - It did not format: `"Last successful sync hh:mm - 17 sources: a ok / b degraded / c blocked / d unreachable / e disabled"`.

---

## 5. Phase B Plan of Action (K1 – K13)

With Phase A complete and zero data modified, we proceed systematically through items K1–K13, committing each step cleanly on `fix/gov-updates-quality`:

1. **K1:** Source status model & transitions (`ok`, `degraded`, `blocked_requires_verification`, `unreachable`, `disabled`), 24h cool-down, header counts, source reset script.
2. **K2:** Real endpoints integration & documentation.
3. **K3:** Deterministic dates (never day 01 unless source states; `date_precision`, `issue_date_source`).
4. **K4:** Genuine document numbers (`doc_number_source`; no `#GSTC-...`).
5. **K5:** Classification (`administrative_not_law`, title casing, operative restrictions).
6. **K6:** e-Gazette ministry allowlist & item-specific URLs.
7. **K7:** Text quality scoring & letter-spaced text repair.
8. **K8:** "New" badge 14-day rule and baseline backfill.
9. **K9:** Category empty states naming unavailable sources.
10. **K10:** Manual circular import dialog & backend endpoint.
11. **K11:** Additional working sources (ICAI IDTC, GSTAT, DoR).
12. **K12:** Data repair script (`scripts/repair_gov_updates.py`).
13. **K13:** Tests, live stack verification, and evidence export.
