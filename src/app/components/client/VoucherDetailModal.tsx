import React, { useState, useEffect, useMemo } from "react";
import {
  FileSpreadsheet,
  CheckCircle2,
  Calendar,
  Building2,
  Wallet,
  Clock,
  FileText,
  Eye,
  Scale,
  Receipt,
  ArrowRight,
  ShieldCheck,
} from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../ui/dialog";
import { Button } from "../ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "../ui/table";
import { StatusBadge } from "../common/StatusBadge";
import { currency } from "../../data/mock";
import { cn } from "../ui/utils";

export interface ParsedTaxHead {
  head: string;
  amount: number;
  formatted: string;
}

export interface ParsedLedgerTransaction {
  id: string;
  date: string;
  partyName: string;
  refNo: string;
  taxableAmount: number | null;
  taxableFormatted: string | null;
  taxBreakdown: ParsedTaxHead[];
  postedAt: string | null;
  account: string;
  type: string;
  isDebit: boolean;
  amount: number;
  debit: number;
  credit: number;
  status: string;
  documentId?: string;
  rawDesc: string;
}

export interface DoubleEntryRow {
  accountCode?: string;
  accountName: string;
  classification: string;
  debit: number | null;
  credit: number | null;
  note?: string;
}

export interface PersistentJournalLine {
  id: string;
  line_number: number;
  account_id: string;
  account_code?: string;
  account_name?: string;
  debit_amount: number;
  credit_amount: number;
  description?: string;
  party_name?: string;
  party_gstin?: string;
  tax_head?: string;
  tax_rate?: number;
}

export interface PersistentJournalDetail {
  id: string;
  client_id: string;
  accounting_record_id?: string;
  document_id?: string;
  entry_number: string;
  entry_date: string;
  entry_type: string;
  status: string;
  narration?: string;
  reference_number?: string;
  total_debit: number;
  total_credit: number;
  is_balanced: boolean;
  posted_at?: string;
  lines: PersistentJournalLine[];
}

/**
 * Intelligent parser that extracts structured financial components
 * from raw ledger descriptions, supporting both pipe-delimited format
 * and legacy descriptions.
 */
export function parseLedgerDescription(
  desc: string | undefined | null,
  referenceNumber: string | undefined | null,
  voucherType: string,
  category: string,
  fallbackAccount: string
): {
  partyName: string;
  refNo: string;
  taxableAmount: number | null;
  taxableFormatted: string | null;
  taxBreakdown: ParsedTaxHead[];
  postedAt: string | null;
  cleanSummary: string;
} {
  const raw = (desc || "").trim();
  // Strip out any legacy [xxx DRAFT] prefix
  const cleaned = raw.replace(/^\[.*?DRAFT\]\s*/i, "").trim();

  let partyName = "";
  let refNo = referenceNumber || "";
  let taxableAmount: number | null = null;
  let taxableFormatted: string | null = null;
  const taxBreakdown: ParsedTaxHead[] = [];
  let postedAt: string | null = null;

  if (cleaned.includes("|")) {
    const parts = cleaned.split("|").map((p) => p.trim()).filter(Boolean);
    for (const part of parts) {
      if (/^Party\s*:\s*/i.test(part)) {
        partyName = part.replace(/^Party\s*:\s*/i, "").trim();
      } else if (/^Ref\s*:\s*/i.test(part)) {
        const foundRef = part.replace(/^Ref\s*:\s*/i, "").trim();
        if (foundRef) refNo = foundRef;
      } else if (/^Taxable\s*:\s*/i.test(part)) {
        const rawTaxable = part.replace(/^Taxable\s*:\s*/i, "").trim();
        taxableFormatted = rawTaxable;
        const num = parseFloat(rawTaxable.replace(/[^\d.-]/g, ""));
        if (!isNaN(num)) taxableAmount = num;
      } else if (/^Posted\s*:\s*/i.test(part)) {
        postedAt = part.replace(/^Posted\s*:\s*/i, "").trim();
      } else if (/(?:CGST|SGST|IGST|Cess)\s*:/i.test(part)) {
        const subParts = part.split(",");
        for (const sub of subParts) {
          const match = sub.trim().match(/^(CGST|SGST|IGST|Cess)\s*:\s*(.*)$/i);
          if (match) {
            const head = match[1].toUpperCase();
            const formatted = match[2].trim();
            const num = parseFloat(formatted.replace(/[^\d.-]/g, ""));
            taxBreakdown.push({
              head,
              amount: isNaN(num) ? 0 : num,
              formatted,
            });
          }
        }
      }
    }
  }

  // If partyName not extracted from pipe syntax:
  if (!partyName) {
    const matchFor = cleaned.match(/^Transaction for\s+(.+)$/i);
    if (matchFor && matchFor[1]) {
      partyName = matchFor[1].trim();
    } else if (cleaned.includes("—") || cleaned.includes(" - ")) {
      const parts = cleaned.split(/[—–-]/).map((s) => s.trim());
      if (parts.length >= 2) {
        if (parts[0].toLowerCase().includes("invoice")) {
          const invMatch = parts[0].match(/#?([A-Za-z0-9_-]+)/);
          if (invMatch && !refNo) refNo = invMatch[1];
          partyName = parts[1];
        } else {
          partyName = parts[parts.length - 1];
        }
      }
    } else if (refNo && (cleaned === `Ref: ${refNo}` || cleaned.startsWith("Ref:"))) {
      partyName = fallbackAccount || "Commercial Entity";
    } else if (cleaned) {
      partyName = cleaned;
    } else {
      partyName = refNo ? `Ref: ${refNo}` : (fallbackAccount || "General Account");
    }
  }

  const cleanSummary = partyName;

  return {
    partyName,
    refNo,
    taxableAmount,
    taxableFormatted,
    taxBreakdown,
    postedAt,
    cleanSummary,
  };
}

/**
 * Generate standard double-entry journal rows adhering to ICAI standards.
 */
export function generateDoubleEntryRows(t: ParsedLedgerTransaction): DoubleEntryRow[] {
  const rows: DoubleEntryRow[] = [];
  const type = (t.type || "").toUpperCase();
  const party = t.partyName || "Party Account";
  const amount = Number(t.amount) || 0;
  const taxable = t.taxableAmount !== null && t.taxableAmount > 0 ? t.taxableAmount : null;
  const taxes = t.taxBreakdown;

  if (type === "SALES" || type === "INCOME") {
    // 1. Debtor / Customer debited for gross amount
    rows.push({
      accountName: `${party} (Sundry Debtors)`,
      classification: "Current Asset / Receivables",
      debit: amount,
      credit: null,
      note: "Gross receivable from customer",
    });

    // 2. Sales Revenue credited for taxable or net turnover
    const revenueAmount = taxable !== null ? taxable : amount;
    rows.push({
      accountName: "Sales Revenue Account",
      classification: "Direct Income / Revenue",
      debit: null,
      credit: revenueAmount,
      note: "Net taxable sales turnover",
    });

    // 3. Output Tax Liabilities credited
    for (const tax of taxes) {
      if (tax.amount > 0) {
        rows.push({
          accountName: `Output ${tax.head} Account`,
          classification: "Duties & Taxes / Current Liability",
          debit: null,
          credit: tax.amount,
          note: `Statutory GST liability on sales`,
        });
      }
    }
  } else if (type === "PURCHASE" || type === "EXPENSE") {
    // 1. Purchase Expense debited for taxable turnover
    const purchaseAmount = taxable !== null ? taxable : amount;
    rows.push({
      accountName: "Purchase Expense Account",
      classification: "Direct Expense / Cost of Sales",
      debit: purchaseAmount,
      credit: null,
      note: "Taxable purchase consideration",
    });

    // 2. Input Tax Credit debited
    for (const tax of taxes) {
      if (tax.amount > 0) {
        rows.push({
          accountName: `Input ${tax.head} Account (ITC)`,
          classification: "Duties & Taxes (asset)",
          debit: tax.amount,
          credit: null,
          note: `Statutory GST input credit claimable`,
        });
      }
    }

    // 3. Creditor / Supplier credited for gross amount
    rows.push({
      accountName: `${party} (Sundry Creditors)`,
      classification: "Trade Payables",
      debit: null,
      credit: amount,
      note: "Gross payable to supplier",
    });
  } else if (type === "PAYMENT" || t.account.includes("TAX") || type.includes("TAX")) {
    rows.push({
      accountName: `${party || "Tax Authority"} Settlement Account`,
      classification: "Liability Settlement",
      debit: amount,
      credit: null,
      note: "Settlement of statutory liability",
    });
    rows.push({
      accountName: "Bank / Treasury Account",
      classification: "Liquid Asset / Bank Account",
      debit: null,
      credit: amount,
      note: "Disbursed via banking channel",
    });
  } else {
    // Journal / General voucher
    if (t.isDebit) {
      rows.push({
        accountName: `${t.account || "Expense / Asset"} Account`,
        classification: "Nominal / Real Account",
        debit: amount,
        credit: null,
      });
      rows.push({
        accountName: `${party || "Bank / Cash"} Account`,
        classification: "Personal / Bank Account",
        debit: null,
        credit: amount,
      });
    } else {
      rows.push({
        accountName: `${party || "Debtor / Bank"} Account`,
        classification: "Personal / Bank Account",
        debit: amount,
        credit: null,
      });
      rows.push({
        accountName: `${t.account || "Income / Revenue"} Account`,
        classification: "Nominal Account",
        debit: null,
        credit: amount,
      });
    }
  }

  return rows;
}

interface VoucherDetailModalProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  voucher: ParsedLedgerTransaction | null;
  onViewSourceDoc?: (docId: string) => void;
}

export function VoucherDetailModal({
  open,
  onOpenChange,
  voucher,
  onViewSourceDoc,
}: VoucherDetailModalProps) {
  const [journalDetail, setJournalDetail] = useState<PersistentJournalDetail | null>(null);
  const [loadingJournal, setLoadingJournal] = useState<boolean>(false);

  useEffect(() => {
    if (!open || !voucher?.id) {
      setJournalDetail(null);
      return;
    }

    let isMounted = true;
    const fetchJournal = async () => {
      setLoadingJournal(true);
      try {
        const token = localStorage.getItem("ca_token") || localStorage.getItem("access_token");
        const base = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";
        const res = await fetch(`${base}/accounting/drafts/${voucher.id}/journal`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (res.ok) {
          const body = await res.json();
          if (isMounted && body?.data && Array.isArray(body.data.lines) && body.data.lines.length > 0) {
            setJournalDetail(body.data);
            return;
          }
        }
      } catch {
        // Fall back gracefully to simulated rows
      } finally {
        if (isMounted) setLoadingJournal(false);
      }
      if (isMounted) setJournalDetail(null);
    };

    fetchJournal();

    return () => {
      isMounted = false;
    };
  }, [open, voucher?.id]);

  const doubleEntryRows: DoubleEntryRow[] = useMemo(() => {
    if (!voucher) return [];
    if (journalDetail && journalDetail.lines && journalDetail.lines.length > 0) {
      return journalDetail.lines.map((l) => {
        let classification = "Nominal / Real Account";
        if (l.account_code) {
          const code = l.account_code;
          if (code === "2010") {
            classification = "Trade Payables";
          } else if (["1210", "1220", "1230", "1060", "1070", "1080"].includes(code)) {
            classification = "Duties & Taxes (asset)";
          } else if (["2110", "2120", "2130", "2140"].includes(code)) {
            classification = "Duties & Taxes (liability)";
          } else if (["1100", "1010"].includes(code)) {
            classification = "Trade Receivables";
          } else {
            const codeNum = parseInt(code, 10);
            if (codeNum >= 1000 && codeNum < 2000) classification = "Current Asset / Receivables";
            else if (codeNum >= 2000 && codeNum < 3000) classification = "Duties & Taxes / Current Liability";
            else if (codeNum >= 3000 && codeNum < 4000) classification = "Equity / Capital";
            else if (codeNum >= 4000 && codeNum < 5000) classification = "Direct Income / Revenue";
            else if (codeNum >= 5000 && codeNum < 6000) classification = "Direct Expense / Cost of Sales";
            else if (codeNum >= 6000) classification = "Indirect Expense / Overheads";
          }
        }
        const rateLabel = l.tax_rate !== undefined && l.tax_rate !== null ? ` (${l.tax_rate}%)` : "";
        return {
          accountCode: l.account_code,
          accountName: (l.account_name || (l.account_code ? `Account ${l.account_code}` : "Ledger Head")) + rateLabel,
          classification,
          debit: Number(l.debit_amount) > 0 ? Number(l.debit_amount) : null,
          credit: Number(l.credit_amount) > 0 ? Number(l.credit_amount) : null,
          note: l.description || (l.party_name ? `Party: ${l.party_name}` : undefined),
        };
      });
    }
    return generateDoubleEntryRows(voucher);
  }, [journalDetail, voucher]);

  if (!voucher) return null;

  const totalDebit = doubleEntryRows.reduce((sum, r) => sum + (r.debit || 0), 0);
  const totalCredit = doubleEntryRows.reduce((sum, r) => sum + (r.credit || 0), 0);
  const isBalanced = Math.abs(totalDebit - totalCredit) < 0.05;

  const voucherType = (voucher.type || "JOURNAL").toUpperCase();

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="!max-w-none w-[min(1100px,95vw)] sm:!max-w-[1100px] max-h-[95vh] overflow-x-hidden overflow-y-auto p-5 sm:p-6 gap-3.5 shadow-2xl border-border/80 bg-card/95 backdrop-blur-md">
        <DialogHeader className="space-y-1.5 pb-2.5 border-b border-border/40">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <div className="flex items-center gap-2.5">
              <div className="size-9 rounded-lg bg-primary/10 flex items-center justify-center text-primary shrink-0">
                <FileSpreadsheet className="size-5" />
              </div>
              <div>
                <DialogTitle className="text-xl font-bold tracking-tight flex items-center gap-2">
                  <span>Accounting Voucher</span>
                  <span
                    className={cn(
                      "text-xs px-2 py-0.5 rounded font-mono font-semibold uppercase tracking-wider",
                      voucherType === "SALES" || voucherType === "INCOME"
                        ? "bg-emerald-500/15 text-emerald-600 dark:text-emerald-400"
                        : voucherType === "PURCHASE" || voucherType === "EXPENSE"
                        ? "bg-rose-500/15 text-rose-600 dark:text-rose-400"
                        : "bg-blue-500/15 text-blue-600 dark:text-blue-400"
                    )}
                  >
                    {voucherType} VOUCHER
                  </span>
                </DialogTitle>
                <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                  Official financial ledger posting record prepared for Chartered Accountant audit.
                </DialogDescription>
              </div>
            </div>

            <div className="flex items-center gap-2 shrink-0">
              <StatusBadge value={voucher.status} />
              {isBalanced && (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                  <CheckCircle2 className="size-3" />
                  Balanced
                </span>
              )}
            </div>
          </div>
        </DialogHeader>

        {/* Voucher Meta Strip */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 py-0.5">
          <div className="p-2.5 rounded-lg bg-muted/40 border border-border/50">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Calendar className="size-3.5 text-primary/70 shrink-0" />
              <span>Voucher Date</span>
            </div>
            <p className="font-mono font-semibold text-sm text-foreground">{voucher.date}</p>
          </div>

          <div className="p-2.5 rounded-lg bg-muted/40 border border-border/50">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <FileText className="size-3.5 text-primary/70 shrink-0" />
              <span>Reference / Invoice #</span>
            </div>
            <p className="font-mono font-semibold text-sm truncate text-foreground" title={voucher.refNo || "N/A"}>
              {voucher.refNo || "N/A"}
            </p>
          </div>

          <div className="p-2.5 rounded-lg bg-muted/40 border border-border/50">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Building2 className="size-3.5 text-primary/70 shrink-0" />
              <span>Party Account</span>
            </div>
            <p className="font-semibold text-sm truncate text-foreground" title={voucher.partyName}>
              {voucher.partyName}
            </p>
          </div>

          <div className="p-2.5 rounded-lg bg-muted/40 border border-border/50">
            <div className="flex items-center gap-1.5 text-xs text-muted-foreground mb-1">
              <Wallet className="size-3.5 text-primary/70 shrink-0" />
              <span>Total Value</span>
            </div>
            <p className="font-mono font-bold text-sm text-foreground">
              {currency(voucher.amount)}
            </p>
          </div>
        </div>

        {/* Double-Entry Ledger Postings Table */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between flex-wrap gap-2">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
              <Scale className="size-3.5 text-primary" />
              Double-Entry Ledger Posting Table
            </h4>
            <div className="flex items-center gap-2">
              {journalDetail ? (
                <span className="inline-flex items-center gap-1 text-[11px] font-medium text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 px-2.5 py-0.5 rounded-full border border-emerald-500/20">
                  <ShieldCheck className="size-3" />
                  Verified Persistent Journal ({journalDetail.entry_number})
                </span>
              ) : (
                <span className="text-[11px] text-muted-foreground">Standard Two-Legged Journal</span>
              )}
            </div>
          </div>

          <div className="border border-border/60 rounded-lg overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow className="bg-muted/50 hover:bg-muted/50 border-b border-border/60">
                  <TableHead className="font-semibold text-xs py-2">Particulars / Ledger Head</TableHead>
                  <TableHead className="font-semibold text-xs py-2 w-[280px]">Classification</TableHead>
                  <TableHead className="font-semibold text-xs py-2 text-right w-[150px]">Debit (₹ Dr)</TableHead>
                  <TableHead className="font-semibold text-xs py-2 text-right w-[150px]">Credit (₹ Cr)</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {doubleEntryRows.map((row, idx) => (
                  <TableRow key={idx} className="hover:bg-muted/30">
                    <TableCell className="py-2">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        {row.accountCode && (
                          <span className="font-mono text-[11px] font-semibold px-1.5 py-0.5 rounded bg-muted text-muted-foreground border border-border/40">
                            {row.accountCode}
                          </span>
                        )}
                        <span className="font-medium text-sm text-foreground">{row.accountName}</span>
                      </div>
                      {row.note && (
                        <div className="text-[11px] text-muted-foreground mt-0.5">{row.note}</div>
                      )}
                    </TableCell>
                    <TableCell className="py-2 text-xs text-muted-foreground">
                      {row.classification}
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono font-medium text-sm text-blue-600 dark:text-blue-400">
                      {row.debit !== null ? currency(row.debit) : "—"}
                    </TableCell>
                    <TableCell className="py-2 text-right font-mono font-medium text-sm text-emerald-600 dark:text-emerald-400">
                      {row.credit !== null ? currency(row.credit) : "—"}
                    </TableCell>
                  </TableRow>
                ))}

                {/* Total / Balance Row */}
                <TableRow className="bg-muted/60 font-semibold border-t-2 border-border">
                  <TableCell className="py-2 text-xs uppercase tracking-wider font-bold">
                    Total
                  </TableCell>
                  <TableCell className="py-2 text-xs text-muted-foreground">
                    {isBalanced ? (
                      <span className="inline-flex items-center text-emerald-600 dark:text-emerald-400 font-medium">
                        <CheckCircle2 className="size-3.5 mr-1" />
                        Balanced Double-Entry
                      </span>
                    ) : (
                      "Unbalanced Entry"
                    )}
                  </TableCell>
                  <TableCell className="py-2 text-right font-mono font-bold text-sm text-blue-600 dark:text-blue-400">
                    {currency(totalDebit)}
                  </TableCell>
                  <TableCell className="py-2 text-right font-mono font-bold text-sm text-emerald-600 dark:text-emerald-400">
                    {currency(totalCredit)}
                  </TableCell>
                </TableRow>
              </TableBody>
            </Table>
          </div>
        </div>

        {/* GST Commercial Breakdown (if taxes present) */}
        {(voucher.taxableFormatted || voucher.taxBreakdown.length > 0) && (
          <div className="p-3 rounded-lg bg-muted/30 border border-border/50 space-y-1.5">
            <div className="flex items-center justify-between">
              <h5 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground flex items-center gap-1.5">
                <Receipt className="size-3.5 text-primary" />
                GST &amp; Tax Assessment Breakdown
              </h5>
              <span className="text-[11px] text-muted-foreground font-mono">Statutory Assessment</span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-0.5">
              <div className="p-2 rounded bg-background border border-border/40">
                <p className="text-[10px] text-muted-foreground uppercase font-medium">Net Taxable Base</p>
                <p className="font-mono font-semibold text-sm text-emerald-600 dark:text-emerald-400">
                  {voucher.taxableFormatted || currency(voucher.amount)}
                </p>
              </div>

              {voucher.taxBreakdown.map((t, i) => (
                <div key={i} className="p-2 rounded bg-background border border-border/40">
                  <p className="text-[10px] text-muted-foreground uppercase font-medium">{t.head} Rate / Amount</p>
                  <p className="font-mono font-semibold text-sm text-blue-600 dark:text-blue-400">
                    {t.formatted}
                  </p>
                </div>
              ))}

              <div className="p-2 rounded bg-background border border-border/40">
                <p className="text-[10px] text-muted-foreground uppercase font-medium">Gross Invoice Amount</p>
                <p className="font-mono font-bold text-sm text-foreground">
                  {currency(voucher.amount)}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Audit Trail & Source Document Card */}
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 p-3 rounded-lg bg-primary/5 border border-primary/20">
          <div className="space-y-0.5 min-w-0">
            <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
              <Clock className="size-3.5 text-primary shrink-0" />
              <span>Audit Trail &amp; Verification Link</span>
            </div>
            <p className="text-xs text-muted-foreground truncate">
              {journalDetail?.posted_at
                ? `Posted to ledger: ${journalDetail.posted_at} • Ref: ${journalDetail.entry_number}`
                : voucher.postedAt
                ? `Posted to ledger: ${voucher.postedAt}`
                : "Posted via FinLedger verified document bridge"}
              {voucher.documentId && ` • Linked Document: DOC-${voucher.documentId.slice(0, 8)}`}
            </p>
            {journalDetail?.narration && (
              <p className="text-[11px] text-muted-foreground/80 italic pt-0.5 truncate">
                Narration: {journalDetail.narration}
              </p>
            )}
          </div>

          {voucher.documentId && onViewSourceDoc && (
            <Button
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 text-xs font-medium shrink-0 border-primary/30 hover:bg-primary/10"
              onClick={() => {
                onOpenChange(false);
                onViewSourceDoc(voucher.documentId!);
              }}
            >
              <Eye className="size-3.5 text-primary" />
              Inspect Source Document
              <ArrowRight className="size-3" />
            </Button>
          )}
        </div>

        <DialogFooter className="pt-1">
          <Button variant="outline" size="sm" className="h-8 text-xs font-medium" onClick={() => onOpenChange(false)}>
            Close Voucher
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
