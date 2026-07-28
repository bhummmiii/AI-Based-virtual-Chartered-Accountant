// ============================================================
// API Endpoints Configuration
// ============================================================

export const API_ENDPOINTS = {
  // Auth
  AUTH: {
    LOGIN: "/auth/login",
    REGISTER: "/auth/register",
    REFRESH: "/auth/refresh",
    LOGOUT: "/auth/logout",
    PROFILE: "/auth/profile",
  },

  // Clients
  CLIENTS: {
    BASE: "/clients",
    BY_ID: (id: string) => `/clients/${id}`,
  },

  // Accounting
  ACCOUNTING: {
    BASE: "/accounting",
    ENTRIES: "/accounting/entries",
    LEDGER: "/accounting/ledger",
    TRIAL_BALANCE: "/accounting/trial-balance",
    BALANCE_SHEET: "/accounting/balance-sheet",
    PROFIT_LOSS: "/accounting/profit-loss",
  },

  // GST
  GST: {
    BASE: "/gst",
    RETURNS: "/gst/returns",
    INVOICES: "/gst/invoices",
    RECONCILIATION: "/gst/reconciliation",
  },

  // Tax
  TAX: {
    BASE: "/tax",
    COMPUTATION: "/tax/computation",
    DEDUCTIONS: "/tax/deductions",
    FILING: "/tax/filing",
  },

  // Audit
  AUDIT: {
    BASE: "/audit",
    CHECKLIST: "/audit/checklist",
    FINDINGS: "/audit/findings",
  },

  // Reports
  REPORTS: {
    BASE: "/reports",
    GENERATE: "/reports/generate",
    EXPORT: "/reports/export",
  },

  // Government Updates
  GOVERNMENT: {
    BASE: "/government",
    UPDATES: "/government/updates",
    NOTIFICATIONS: "/government/notifications",
  },

  // AI Chatbot
  CHATBOT: {
    BASE: "/chatbot",
    SEND: "/chatbot/send",
    HISTORY: "/chatbot/history",
  },

  // OCR
  OCR: {
    BASE: "/ocr",
    SCAN: "/ocr/scan",
    EXTRACT: "/ocr/extract",
  },

  // Translation
  TRANSLATION: {
    BASE: "/translation",
    TRANSLATE: "/translation/translate",
    DETECT: "/translation/detect",
  },
} as const;
