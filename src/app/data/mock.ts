// Centralized mock data for the AI Chartered Accountant Assistant.
// All figures are illustrative sample data (INR).

export const currency = (n: number) =>
  new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    maximumFractionDigits: 0,
  }).format(n);

export const compact = (n: number) =>
  new Intl.NumberFormat("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1,
    style: "currency",
    currency: "INR",
  }).format(n);

export const kpis = {
  revenue: 8452000,
  expenses: 4218500,
  profit: 4233500,
  gstDue: 386400,
  taxDue: 512000,
  pendingAudits: 7,
  healthScore: 82,
  riskScore: 24,
};

export const cashFlow = [
  { month: "Jan", inflow: 620000, outflow: 380000 },
  { month: "Feb", inflow: 710000, outflow: 420000 },
  { month: "Mar", inflow: 890000, outflow: 510000 },
  { month: "Apr", inflow: 640000, outflow: 470000 },
  { month: "May", inflow: 920000, outflow: 530000 },
  { month: "Jun", inflow: 1050000, outflow: 610000 },
  { month: "Jul", inflow: 980000, outflow: 560000 },
  { month: "Aug", inflow: 1120000, outflow: 640000 },
];

export const expenseBreakdown = [
  { name: "Salaries", value: 1650000, color: "var(--chart-1)" },
  { name: "Operations", value: 920000, color: "var(--chart-2)" },
  { name: "Marketing", value: 610000, color: "var(--chart-3)" },
  { name: "Software", value: 480000, color: "var(--chart-4)" },
  { name: "Misc", value: 558500, color: "var(--chart-5)" },
];

export const revenueTrend = [
  { month: "Jan", value: 620000 },
  { month: "Feb", value: 710000 },
  { month: "Mar", value: 890000 },
  { month: "Apr", value: 640000 },
  { month: "May", value: 920000 },
  { month: "Jun", value: 1050000 },
  { month: "Jul", value: 980000 },
  { month: "Aug", value: 1120000 },
];

export type Client = {
  id: string;
  name: string;
  company: string;
  type: "Company" | "Individual" | "LLP" | "Partnership";
  gstin: string;
  revenue: number;
  status: "Active" | "Review" | "Inactive";
  gst: "Filed" | "Due" | "Overdue";
  audit: "Passed" | "In Progress" | "Pending" | "Flagged";
  tax: "Filed" | "Due" | "Overdue";
  risk: "Low" | "Medium" | "High";
  lastActivity: string;
  avatar: string;
  // Extended fields (stored in DB, not shown on workspace cards)
  clientType?: "Monthly" | "Quarterly";
  contactNumber?: string;
  emailAddress?: string;
  location?: string;
};

export const clients: Client[] = [
  { id: "C-1042", name: "Ananya Rao", company: "Nimbus Technologies", type: "Company", gstin: "27AABCN1234R1Z5", revenue: 2450000, status: "Active", gst: "Filed", audit: "In Progress", tax: "Filed", risk: "Low", lastActivity: "2 hours ago", avatar: "AR" },
  { id: "C-1043", name: "Rohit Mehta", company: "Mehta & Sons LLP", type: "LLP", gstin: "24AAFCM5678K1Z2", revenue: 1180000, status: "Active", gst: "Due", audit: "Passed", tax: "Due", risk: "Medium", lastActivity: "Yesterday", avatar: "RM" },
  { id: "C-1044", name: "Priya Nair", company: "Coastal Exports", type: "Partnership", gstin: "32AACCP9012L1Z8", revenue: 3620000, status: "Review", gst: "Overdue", audit: "Flagged", tax: "Overdue", risk: "High", lastActivity: "3 days ago", avatar: "PN" },
  { id: "C-1045", name: "Vikram Singh", company: "Singh Retail Pvt Ltd", type: "Company", gstin: "07AADCS3456M1Z1", revenue: 890000, status: "Active", gst: "Filed", audit: "Pending", tax: "Filed", risk: "Low", lastActivity: "5 days ago", avatar: "VS" },
  { id: "C-1046", name: "Meera Iyer", company: "Iyer Consulting", type: "Individual", gstin: "29AACPI7890N1Z4", revenue: 540000, status: "Inactive", gst: "Filed", audit: "Passed", tax: "Filed", risk: "Low", lastActivity: "2 weeks ago", avatar: "MI" },
  { id: "C-1047", name: "Arjun Kapoor", company: "Kapoor Textiles", type: "Company", gstin: "08AADCK2345P1Z9", revenue: 2960000, status: "Active", gst: "Due", audit: "In Progress", tax: "Due", risk: "Medium", lastActivity: "6 hours ago", avatar: "AK" },
];

export type Txn = {
  id: string;
  date: string;
  desc: string;
  account: string;
  type: "Income" | "Expense";
  amount: number;
  status: "Reconciled" | "Pending";
};

export const transactions: Txn[] = [
  { id: "TXN-9001", date: "2026-07-21", desc: "Invoice #INV-2210 — Nimbus Tech", account: "Sales Revenue", type: "Income", amount: 245000, status: "Reconciled" },
  { id: "TXN-9002", date: "2026-07-20", desc: "AWS Cloud Services", account: "Software", type: "Expense", amount: 68400, status: "Reconciled" },
  { id: "TXN-9003", date: "2026-07-19", desc: "Office Rent — July", account: "Operations", type: "Expense", amount: 120000, status: "Reconciled" },
  { id: "TXN-9004", date: "2026-07-18", desc: "Consulting — Coastal Exports", account: "Services", type: "Income", amount: 380000, status: "Pending" },
  { id: "TXN-9005", date: "2026-07-17", desc: "Payroll — July batch", account: "Salaries", type: "Expense", amount: 540000, status: "Reconciled" },
  { id: "TXN-9006", date: "2026-07-16", desc: "Google Ads Campaign", account: "Marketing", type: "Expense", amount: 96000, status: "Pending" },
  { id: "TXN-9007", date: "2026-07-15", desc: "Invoice #INV-2209 — Kapoor Textiles", account: "Sales Revenue", type: "Income", amount: 412000, status: "Reconciled" },
];

export const deadlines = [
  { id: 1, title: "GSTR-3B Filing", date: "20 Aug 2026", tag: "GST", priority: "high" },
  { id: 2, title: "TDS Payment Q1", date: "07 Aug 2026", tag: "Tax", priority: "high" },
  { id: 3, title: "Audit Report — Nimbus", date: "28 Aug 2026", tag: "Audit", priority: "medium" },
  { id: 4, title: "Advance Tax Instalment", date: "15 Sep 2026", tag: "Tax", priority: "low" },
];

export const aiSuggestions = [
  { id: 1, text: "Coastal Exports shows 3 duplicate vendor payments totalling ₹1.2L — review before filing.", severity: "danger" },
  { id: 2, text: "You can claim ₹86,400 additional ITC from unmatched GSTR-2B invoices.", severity: "success" },
  { id: 3, text: "New regime saves Vikram Singh ₹42,000 vs old regime this year.", severity: "info" },
];

export const notifications = [
  { id: 1, title: "GSTR-3B due in 5 days", body: "For 4 clients across Maharashtra & Delhi.", time: "2h ago", type: "warning", unread: true },
  { id: 2, title: "Audit flag raised", body: "Coastal Exports — suspicious round-figure entries detected.", time: "5h ago", type: "danger", unread: true },
  { id: 3, title: "Invoice OCR complete", body: "12 invoices processed with 98% avg confidence.", time: "1d ago", type: "success", unread: false },
  { id: 4, title: "New GST circular published", body: "Circular 214/8/2026 — e-invoicing threshold update.", time: "2d ago", type: "info", unread: false },
];

export const todaysTasks = [
  { id: 1, title: "Finalise GSTR-3B for Nimbus Technologies", due: "By 5:00 PM", done: false, tag: "GST" },
  { id: 2, title: "Review flagged entries — Coastal Exports", due: "By EOD", done: false, tag: "Audit" },
  { id: 3, title: "Call Rohit Mehta re: pending TDS", due: "2:30 PM", done: false, tag: "Tax" },
  { id: 4, title: "Upload signed balance sheet — Kapoor Textiles", due: "Completed", done: true, tag: "Docs" },
];

export const recentActivity = [
  { id: 1, who: "Ananya Rao", action: "uploaded 12 purchase invoices", client: "Nimbus Technologies", time: "2 hours ago", type: "upload" },
  { id: 2, who: "You", action: "filed GSTR-1 for June", client: "Mehta & Sons LLP", time: "Yesterday", type: "filing" },
  { id: 3, who: "System", action: "flagged 3 duplicate payments", client: "Coastal Exports", time: "3 days ago", type: "alert" },
  { id: 4, who: "You", action: "generated audit report", client: "Singh Retail Pvt Ltd", time: "5 days ago", type: "report" },
  { id: 5, who: "Arjun Kapoor", action: "shared bank statement Q1", client: "Kapoor Textiles", time: "6 days ago", type: "upload" },
];

export const clientInvoices = [
  { id: "INV-2210", date: "21 Jul 2026", party: "Zenith Corp", type: "Sales", amount: 245000, status: "Reconciled" },
  { id: "INV-2209", date: "15 Jul 2026", party: "Orbit Media", type: "Sales", amount: 412000, status: "Reconciled" },
  { id: "BILL-1188", date: "12 Jul 2026", party: "AWS India", type: "Purchase", amount: 68400, status: "Pending" },
  { id: "BILL-1187", date: "08 Jul 2026", party: "WeWork", type: "Purchase", amount: 120000, status: "Reconciled" },
  { id: "INV-2208", date: "02 Jul 2026", party: "Delta Systems", type: "Sales", amount: 186000, status: "Pending" },
];

export const clientDocuments = [
  { name: "Balance Sheet FY26.pdf", type: "Financials", size: "1.2 MB", date: "18 Jul 2026" },
  { name: "GSTR-3B June.pdf", type: "GST", size: "480 KB", date: "11 Jul 2026" },
  { name: "Bank Statement Q1.csv", type: "Bank", size: "2.1 MB", date: "08 Jul 2026" },
  { name: "PAN Card.jpg", type: "KYC", size: "320 KB", date: "02 Apr 2026" },
  { name: "Incorporation Certificate.pdf", type: "KYC", size: "890 KB", date: "02 Apr 2026" },
];

export const clientHistory = [
  { time: "Today, 10:42", event: "AI audit scan initiated", type: "info" },
  { time: "Yesterday", event: "GSTR-1 filed for June 2026", type: "success" },
  { time: "08 Jul 2026", event: "12 invoices uploaded via OCR", type: "info" },
  { time: "20 Jun 2026", event: "GSTR-3B filed for May 2026", type: "success" },
  { time: "02 Apr 2026", event: "Client onboarded to workspace", type: "info" },
];

export const gstReturns = [
  { period: "Jul 2026", form: "GSTR-1", due: "11 Aug 2026", status: "Pending", tax: 386400 },
  { period: "Jun 2026", form: "GSTR-3B", due: "20 Jul 2026", status: "Filed", tax: 341200 },
  { period: "Jun 2026", form: "GSTR-1", due: "11 Jul 2026", status: "Filed", tax: 341200 },
  { period: "May 2026", form: "GSTR-3B", due: "20 Jun 2026", status: "Filed", tax: 298700 },
];

export const hsnCodes = [
  { code: "8471", desc: "Automatic data processing machines (computers)", rate: 18 },
  { code: "9983", desc: "Other professional, technical & business services", rate: 18 },
  { code: "6109", desc: "T-shirts, singlets & vests, knitted", rate: 5 },
  { code: "2106", desc: "Food preparations not elsewhere specified", rate: 12 },
  { code: "3004", desc: "Medicaments (therapeutic use)", rate: 12 },
];

export const auditRisks = [
  { month: "Feb", risk: 18 },
  { month: "Mar", risk: 22 },
  { month: "Apr", risk: 31 },
  { month: "May", risk: 27 },
  { month: "Jun", risk: 24 },
  { month: "Jul", risk: 24 },
];

export const fraudIndicators = [
  { label: "Duplicate transactions", value: 3, severity: "danger" },
  { label: "Round-figure entries", value: 8, severity: "warning" },
  { label: "After-hours postings", value: 5, severity: "warning" },
  { label: "Missing supporting docs", value: 12, severity: "danger" },
];

export const auditTimeline = [
  { time: "10:42", event: "AI scan initiated on Coastal Exports ledger", type: "info" },
  { time: "10:44", event: "3 duplicate vendor payments detected", type: "danger" },
  { time: "10:45", event: "8 round-figure entries flagged for review", type: "warning" },
  { time: "10:47", event: "Cross-verified 214 invoices against GSTR-2B", type: "success" },
  { time: "10:49", event: "Financial health score computed: 68/100", type: "info" },
];

export const govRules = [
  { id: 1, title: "E-invoicing threshold reduced to ₹5 Cr turnover", tag: "GST", date: "18 Jul 2026", summary: "Businesses above ₹5 crore annual turnover must now generate e-invoices for all B2B supplies.", bookmarked: true },
  { id: 2, title: "New Section 44ADA presumptive limit for professionals", tag: "Income Tax", date: "12 Jul 2026", summary: "Presumptive taxation limit raised to ₹75 lakh for eligible professionals, subject to cash-receipt conditions.", bookmarked: false },
  { id: 3, title: "TDS on virtual digital assets clarified", tag: "TDS", date: "05 Jul 2026", summary: "CBDT clarifies 1% TDS applicability on peer-to-peer VDA transfers via exchanges.", bookmarked: false },
  { id: 4, title: "Budget 2026 — standard deduction increased", tag: "Budget", date: "01 Jul 2026", summary: "Standard deduction under the new regime increased to ₹75,000 for salaried taxpayers.", bookmarked: true },
];

export const chatHistory = [
  { id: 1, title: "GST ITC reconciliation help", time: "Today" },
  { id: 2, title: "Old vs new regime for ₹18L salary", time: "Today" },
  { id: 3, title: "Depreciation on plant & machinery", time: "Yesterday" },
  { id: 4, title: "Section 80C deduction limits", time: "3 days ago" },
];

export const suggestedPrompts = [
  "Summarise this client's tax liability for FY26",
  "Which invoices are missing from GSTR-2B?",
  "Explain the latest e-invoicing circular simply",
  "Compute advance tax for Q2 for Nimbus Technologies",
];
