# Government Updates Quality Audit Spot Check (K13 Evidence)

**Date:** 2026-10-14
**Total Visible Updates:** 61
**Total Sources:** 17 (6 ok / 0 degraded / 6 blocked / 5 unreachable / 0 disabled)

## Verified Quality Invariants (K1–K12):

1. **K1 Source Status Model:** Mutually exclusive statuses summing exactly to 17 total sources in live database.
2. **K2 Real Endpoints & Diagnostics:** WAF 403 challenge endpoints documented with owner next steps.
3. **K3 Deterministic Dates:** 57th GST Council meeting date = `2026-10-08`, 56th = `2025-09-03`, newsletters have `date_precision = month`. Zero guessed day-01 dates.
4. **K4 Genuine Doc Numbers:** `#GSTC-57TH` and synthesized URL/ICAI slugs eliminated. Doc numbers occur verbatim or are null.
5. **K5 Administrative Items:** Vacancies, exams, and awards hidden behind `show_administrative` toggle; operative tag restricted to law-making authorities.
6. **K6 e-Gazette Ministries & Direct Links:** Non-tax ministries (Railways, Defence) hidden; listing links marked `listing_only`.
7. **K7 Text Quality Scoring:** Letter-spaced text in GSTC newsletter repaired; unreadable items display graceful empty state.
8. **K8 14-Day New Badge Rule:** Updates older than 14 days or with NULL date marked `backfilled = true` and `is_new = false`.
9. **K9 Category Empty States:** Categories without working sources show informative banner naming blocked/unreachable sources.
10. **K10 Manual Import:** Working manual circular import with official statutory domain validation, text extraction, deduplication, and audit logging.

## Sample Spot Check Cards (First 10):

### 1. Announcement - Last Opportunity for Submission of MEF 2026-27 - (14-10-2026)
- **Source:** Institute of Chartered Accountants of India (`icai_announcements`)
- **Category:** ACCOUNTING | **Doc Type:** other | **Legal Status:** unknown
- **Issue Date:** 2026-10-14 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `True` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://www.icai.org/post/mef141026n](https://www.icai.org/post/mef141026n)

### 2. Open Market Operation (OMO) – Sale of Government of India  Securities held on Oct 13, 2026: Cut-Offs
- **Source:** Reserve Bank of India (Press Releases) (`rbi_pressreleases`)
- **Category:** BANKING | **Doc Type:** press_release | **Legal Status:** press_release_not_law
- **Issue Date:** 2026-10-13 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `True` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=63796](https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=63796)

### 3. Detailed Result: OMO Sale Auction held on Oct 13, 2026 and Settlement on Oct 14, 2026
- **Source:** Reserve Bank of India (Press Releases) (`rbi_pressreleases`)
- **Category:** BANKING | **Doc Type:** press_release | **Legal Status:** press_release_not_law
- **Issue Date:** 2026-10-13 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `True` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=63798](https://www.rbi.org.in/scripts/BS_PressReleaseDisplay.aspx?prid=63798)

### 4. FAQs on recommendations of GST Council made in its 57th meeting on 08.10.2026.
- **Source:** Goods and Services Tax Council (`gstcouncil`)
- **Category:** GST | **Doc Type:** faq | **Legal Status:** advisory
- **Issue Date:** 2026-10-08 (Precision: `day`, Source: `None`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `True` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://gstcouncil.gov.in/sites/default/files/2026-10/faqs_on_recommendations_made_in_57th_gst_council_meeting.pdf](https://gstcouncil.gov.in/sites/default/files/2026-10/faqs_on_recommendations_made_in_57th_gst_council_meeting.pdf)

### 5. Press Release Regarding Recommendations of the 57th Meeting of the GST Council
- **Source:** Goods and Services Tax Council (`gstcouncil`)
- **Category:** GST | **Doc Type:** press_release | **Legal Status:** press_release_not_law
- **Issue Date:** 2026-10-08 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `True` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://gstcouncil.gov.in/sites/default/files/2026-10/press_release_0.pdf](https://gstcouncil.gov.in/sites/default/files/2026-10/press_release_0.pdf)

### 6. Invitation for contribution to Question Bank in respect of Advanced Integrated Course on Information Technology and Soft Skills (AICITSS) - Advanced IT test. - (01-10-2026)
- **Source:** Institute of Chartered Accountants of India (`icai_announcements`)
- **Category:** ACCOUNTING | **Doc Type:** event_or_exam | **Legal Status:** unknown
- **Issue Date:** 2026-10-01 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `True` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://www.icai.org/post/icai-exam-announcement-01102026](https://www.icai.org/post/icai-exam-announcement-01102026)

### 7. Announcement for Extension of Last Date for Submitting MEF 2026-27 from 29th August to 9th September, 2026 - (28-08-2026)
- **Source:** Institute of Chartered Accountants of India (`icai_announcements`)
- **Category:** ACCOUNTING | **Doc Type:** other | **Legal Status:** unknown
- **Issue Date:** 2026-08-28 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `False` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://www.icai.org/post/mef280826](https://www.icai.org/post/mef280826)

### 8. Important Announcement - Self-Paced Module Test - (24-08-2026)
- **Source:** Institute of Chartered Accountants of India (`icai_announcements`)
- **Category:** ACCOUNTING | **Doc Type:** event_or_exam | **Legal Status:** unknown
- **Issue Date:** 2026-08-24 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `False` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://www.icai.org/post/exam-spmt-24082026](https://www.icai.org/post/exam-spmt-24082026)

### 9. 77th Annual Report and Accounts of the Institute for the year 2025-26 - (06-08-2026)
- **Source:** Institute of Chartered Accountants of India (`icai_announcements`)
- **Category:** ACCOUNTING | **Doc Type:** other | **Legal Status:** unknown
- **Issue Date:** 2026-08-06 (Precision: `day`, Source: `None`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `False` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://www.icai.org/post/77th-annual-report-and-accounts-icai-year-2025-26](https://www.icai.org/post/77th-annual-report-and-accounts-icai-year-2025-26)

### 10. Notice for the 56th GST Council Meeting to be held on 3rd and 4th September, 2025- reg
- **Source:** Goods and Services Tax Council (`gstcouncil`)
- **Category:** GST | **Doc Type:** other | **Legal Status:** unknown
- **Issue Date:** 2025-09-03 (Precision: `day`, Source: `listing`)
- **Doc Number:** `None` (Source: `None`)
- **Is New:** `False` | **Link Quality:** `direct_document` | **Text Status:** `ok`
- **URL:** [https://gstcouncil.gov.in/sites/default/files/2025-08/meeting_notice_56th_gst_council_meeting_0.pdf](https://gstcouncil.gov.in/sites/default/files/2025-08/meeting_notice_56th_gst_council_meeting_0.pdf)

