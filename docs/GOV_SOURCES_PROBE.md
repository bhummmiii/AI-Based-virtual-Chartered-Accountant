# Government Sources Probe Report (Phase A)
**Date of Probe:** 2026-10-12  
**Probing Bot:** `FinLedgerBot/1.0 (+compliance@finledger.ai)`  
**Protocol Compliance:** Respects `robots.txt` (`urllib.robotparser`), min 3.2s per-host delay, max 1 concurrent connection per host, 20s timeouts, no CAPTCHA/WAF solving (R5, R6).

---

## 1. Current State Audit (A1)

| Component | Location | Current State & Behavior |
| :--- | :--- | :--- |
| **Sample Cards (4 items)** | `src/app/pages/GovRules.tsx` & `src/app/data/mock.ts` | 4 hardcoded cards loaded from `mock.ts` (`govRules` array). Includes re-dated/inaccurate items (e.g. "E-invoicing threshold reduced to Rs 5 Cr turnover" dated 18 Jul 2026). |
| **Dashboard Notifications** | `src/app/services/notification.service.ts` & `backend/app/services/notification_service.py` | Hardcoded fallback message `"Circular 214/8/2026 — Clarification on e-invoicing thresholds & statutory reporting guidelines."` when `government_rules` table has no items or fallback is triggered. |
| **Saved / Bookmarks Storage** | `src/app/pages/GovRules.tsx` | Purely in-memory React state (`useState<Record<number, boolean>>`). Not persisted per user in DB or localStorage. Resets on page reload. |
| **Frontend Fetching** | `src/app/pages/GovRules.tsx` | Currently does NOT make any API calls. Directly filters the static mock array. |
| **Gemini Integration** | `backend/app/services/chatbot_service.py` & `backend/app/services/ai_assistant/engine.py` | Uses `google-genai` SDK (`genai.Client(api_key=settings.GEMINI_API_KEY)`) with model `settings.GEMINI_MODEL` (`gemini-flash-lite-latest`). |

---

## 2. Live Source Probe Results (A2 & A2b)

Probed live against production domains on 2026-10-12 following R5/R6 scraping rules.

| Source Name | Code | Method | robots_ok | captcha / WAF | Items Found | Decision | Reason | Terms of Use Link / Note |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Reserve Bank of India (Notifications)** | `rbi_notifications` | RSS | True | False (clean) | 9 | **ENABLE** | Clean XML feed, valid dates up to 10-Oct-2026, no auth/WAF. | [RBI Terms](https://rbi.org.in/scripts/Disclaimer.aspx): Public notifications. |
| **Reserve Bank of India (Press Releases)** | `rbi_pressreleases` | RSS | True | False (clean) | 10 | **ENABLE** | Clean XML feed, real-time items from 12-Oct-2026. | [RBI Terms](https://rbi.org.in/scripts/Disclaimer.aspx): Public releases. |
| **GST Council** | `gstcouncil` | HTML Listing / PDF | True | False (clean) | 20+ | **ENABLE** | Clean HTML listing, downloadable PDFs, 57th Meeting decisions (Oct 2026). | [GST Council Policy](https://gstcouncil.gov.in/website-policy): Open access. |
| **Institute of Chartered Accountants of India** | `icai_announcements` | HTML Listing | True (404) | False (clean) | 15+ | **ENABLE** | Accessible listing with post links, full announcement body, dates up to Oct 2026. | [ICAI Disclaimer](https://www.icai.org/post/16585): Public notices. |
| **e-Gazette of India (Recent Extraordinary)** | `egazette_recent` | HTML Listing | True (404) | False (clean on homepage) | 4+ | **LISTING-ONLY** | Homepage table parsed directly without search (search has ASP.NET error/captcha). | [eGazette Terms](https://egazette.gov.in): Gazette notifications. |
| **National Financial Reporting Authority** | `nfra_orders` | HTML Listing | True | False (clean) | 2+ | **ENABLE** | Clean HTML, orders under Section 132(4) Companies Act. | [NFRA Policy](https://nfra.gov.in): Open statutory orders. |
| **Securities and Exchange Board of India** | `sebi_circulars` | HTML Listing | True | False (clean on listing) | 22 | **ENABLE** (Optional Tier 2) | Clean table listing on HomeAction listing endpoint, dates up to 12-Oct-2026. | [SEBI Terms](https://www.sebi.gov.in): Public circulars. |
| **CBIC Tax Information Publisher** | `cbic_taxinfo` | HTML Listing / PDF | Timeout | Unreachable | 0 | **DISABLED** | Host `taxinformation.cbic.gov.in` (163.227.109.58) timed out on ports 80/443. | N/A (unreachable) |
| **CBIC GST Portal** | `cbic_gst` | HTML Listing | Timeout | Unreachable | 0 | **DISABLED** | Host `cbic-gst.gov.in` (163.227.109.192) timed out. | N/A (unreachable) |
| **GST Portal News & Updates** | `gstn_news` | HTML Listing | HTTP 403 | True (WAF challenge) | 0 | **BLOCKED** | HTTP 403 Akamai/Cloudflare bot challenge on `/newsandupdates`. R6 requires stop. | [GST Terms](https://www.gst.gov.in/termsandconditions) |
| **Income Tax Department RSS** | `incometax_feed` | RSS / HTML | HTTP 403 | True (WAF challenge) | 0 | **BLOCKED** | HTTP 403 Imperva/Akamai challenge on `/tax-feeds` and communications pages. | [ITD Terms](https://incometaxindia.gov.in) |
| **PIB Press Information Bureau** | `pib_rss` | RSS | Timeout | HTTP 403 / Timeout | 0 | **BLOCKED** | Connect timeout / 403 on `pib.gov.in/RssMain.aspx`. | [PIB Terms](https://pib.gov.in) |
| **Ministry of Corporate Affairs** | `mca` | HTML Listing | HTTP 403 | True (WAF block) | 0 | **BLOCKED** | HTTP 403 WAF block on `www.mca.gov.in`. | [MCA Terms](https://www.mca.gov.in) |
| **Ministry of Finance** | `finmin` | HTML Listing | Timeout | Unreachable | 0 | **DISABLED** | Connection timed out to `finmin.gov.in`. | N/A (unreachable) |
| **Department of Revenue** | `dor` | HTML Listing | Timeout | Unreachable | 0 | **DISABLED** | Connection timed out to `dor.gov.in`. | N/A (unreachable) |
| **Union Budget of India** | `indiabudget` | HTML Listing | HTTP 403 | True (WAF block) | 0 | **BLOCKED** | HTTP 403 WAF block on `indiabudget.gov.in`. | [IndiaBudget](https://indiabudget.gov.in) |
| **Maharashtra State GST** | `mahagst` | HTML Listing | Timeout | Unreachable | 0 | **DISABLED** | Timeout on homepage; subpaths 404. | [MahaGST](https://mahagst.gov.in) |

---

## 3. Sample Real Items Verified During Probe

### RBI Notifications RSS (`rbi_notifications`)
1. **Title:** Risk Management and Inter-Bank Dealings - Foreign Exchange Risk Reserve  
   **Date:** 2026-10-10  
   **Doc Number:** RBI/2026-27/82 (Id=13738)  
   **URL:** `https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=13738&Mode=0`
2. **Title:** Section 42(1) of the Reserve Bank of India Act, 1934 - Change in Daily Minimum Cash Reserve Maintenance Requirement  
   **Date:** 2026-10-09  
   **Doc Number:** RBI/2026-27/80 (Id=13736)  
   **URL:** `https://www.rbi.org.in/scripts/NotificationUser.aspx?Id=13736&Mode=0`

### RBI Press Releases RSS (`rbi_pressreleases`)
1. **Title:** Money Market Operations as on October 11, 2026  
   **Date:** 2026-10-12  
   **Doc Number:** PR 63788  
   **URL:** `https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=63788`
2. **Title:** RBI announces special window for Public Sector Oil Marketing Companies to meet dollar requirements  
   **Date:** 2026-10-10  
   **Doc Number:** PR 63784  
   **URL:** `https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=63784`

### GST Council (`gstcouncil`)
1. **Title:** Press Release Regarding Recommendations of the 57th Meeting of the GST Council  
   **Date:** 2026-10-08  
   **Doc Number:** 57th-GSTC-REC  
   **URL:** `https://gstcouncil.gov.in/sites/default/files/2026-10/press_release_0.pdf`
2. **Title:** FAQs on recommendations of GST Council made in its 57th meeting on 08.10.2026  
   **Date:** 2026-10-08  
   **Doc Number:** 57th-GSTC-FAQ  
   **URL:** `https://gstcouncil.gov.in/sites/default/files/2026-10/faqs_on_recommendations_made_in_57th_gst_council_meeting.pdf`

### ICAI Announcements (`icai_announcements`)
1. **Title:** Opening of Nominations for the 20th ICAI Awards - (05-10-2026)  
   **Date:** 2026-10-05  
   **Doc Number:** ICAI/CMIB/2026/20  
   **URL:** `https://www.icai.org/post/cmib-20th-icai-award-2026-27`
2. **Title:** Important Announcement - Self-Paced Module Test - (24-08-2026)  
   **Date:** 2026-08-24  
   **Doc Number:** ICAI/EXAM/SPMT/2026  
   **URL:** `https://www.icai.org/post/exam-spmt-24082026`

### e-Gazette Extraordinary (`egazette_recent`)
1. **Title:** Ministry of Defence DESW Gazette Notification  
   **Date:** 2026-10-12  
   **Doc Number:** CG-DL-E-12102026-277060  
   **URL:** `https://egazette.gov.in`
2. **Title:** Ministry of Road Transport and Highways Publication under Section 3A  
   **Date:** 2026-10-12  
   **Doc Number:** CG-DL-E-12102026-277058  
   **URL:** `https://egazette.gov.in`

### SEBI Circulars (`sebi_circulars`)
1. **Title:** Securities and Exchange Board of India (Certification of Associated Persons in the Securities Markets) (Amendment) Regulations, 2026  
   **Date:** 2026-10-12  
   **Doc Number:** SEBI/LAD-NRO/GN/2026/198  
   **URL:** `https://www.sebi.gov.in/sebiweb/home/HomeAction.do?doListing=yes&sid=1&smid=0&ssid=0`

---

## 4. Phase B Enablement Strategy

In accordance with Hard Rules R5 & R6:
- Sources enabled in the registry:
  1. `rbi_notifications` (Tier 1, RSS, Method: `rss`)
  2. `rbi_pressreleases` (Tier 1, RSS, Method: `rss`)
  3. `gstcouncil` (Tier 1, HTML Listing & PDF, Method: `html_listing`)
  4. `icai_announcements` (Tier 2, HTML Listing, Method: `html_listing`)
  5. `egazette_recent` (Tier 2, HTML Listing, Method: `html_listing` homepage only)
  6. `nfra_orders` (Tier 2, HTML Listing, Method: `html_listing`)
  7. `sebi_circulars` (Tier 2, HTML Listing, Method: `html_listing`)
- Sources marked `blocked_requires_verification` or `disabled` in the registry:
  - `cbic_taxinfo`, `cbic_gst`, `gstn_news`, `incometax_feed`, `pib_rss`, `mca`, `finmin`, `dor`, `indiabudget`, `mahagst`.
- Any blocked source is logged with status `blocked_requires_verification`, cooling off for 24h, surfaced transparently in the Source Health dashboard panel.
