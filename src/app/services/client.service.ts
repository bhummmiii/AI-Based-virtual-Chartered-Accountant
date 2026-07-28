/**
 * client.service.ts — All client API calls for the Workspace module.
 *
 * Backend now uses UUID primary keys.
 * db_id is a UUID string (e.g. "550e8400-e29b-41d4-a716-446655440000").
 * client_code is the human-readable display id (e.g. "CLI-001").
 *
 * The backend returns ClientCardResponse shaped to match the React
 * Client type (id, name, company, type, gstin, revenue, status,
 * gst, audit, tax, risk, lastActivity, avatar) plus db_id (UUID string).
 */

import api from "./api";
import type { Client } from "../data/mock";

// ── Backend card type ─────────────────────────────────────────
export interface ClientCard extends Client {
  /** UUID string — used for PUT / DELETE / dashboard API calls. */
  db_id: string;
}

// ── Paginated list ────────────────────────────────────────────
export interface PaginatedClients {
  items: ClientCard[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── Query params ──────────────────────────────────────────────
export interface GetClientsParams {
  page?: number;
  page_size?: number;
  search?: string;
  sort_by?: string;
  sort_order?: "asc" | "desc";
  status?: string;
  risk_level?: string;
}

// ── Full dashboard (GET /clients/{uuid}) ──────────────────────
export interface ClientProfile {
  id: string;            // UUID
  client_code: string;
  company_name: string;
  contact_person: string;
  client_type: string;
  email: string | null;
  phone: string | null;
  gst_number: string | null;
  pan_number: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  country: string | null;
  industry: string | null;
  risk_level: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface GSTRecord {
  id: string;
  client_id: string;
  gst_period: string;
  gst_type: string;
  taxable_amount: string;
  cgst: string;
  sgst: string;
  igst: string;
  total_tax: string;
  filing_status: string;
  due_date: string | null;
  created_at: string;
}

export interface TaxRecord {
  id: string;
  client_id: string;
  financial_year: string;
  tax_type: string;
  taxable_income: string;
  tds: string;
  advance_tax: string;
  total_tax: string;
  status: string;
  created_at: string;
}

export interface AuditReport {
  id: string;
  client_id: string;
  audit_type: string;
  audit_status: string;
  risk_score: string | null;
  findings: string | null;
  recommendations: string | null;
  created_at: string;
}

export interface Invoice {
  id: string;
  client_id: string;
  invoice_number: string;
  vendor_name: string;
  invoice_date: string;
  amount: string;
  currency: string;
  ocr_text: string | null;
  translated_text: string | null;
  created_at: string;
}

export interface Document {
  id: string;
  client_id: string;
  file_name: string;
  file_type: string;
  storage_path: string;
  uploaded_at: string;
}

export interface AccountingRecord {
  id: string;
  client_id: string;
  transaction_date: string;
  voucher_type: string;
  description: string | null;
  debit: string;
  credit: string;
  category: string | null;
  created_at: string;
}

export interface ClientDashboard {
  client:     ClientProfile;
  gst:        GSTRecord[];
  tax:        TaxRecord[];
  audit:      AuditReport[];
  invoices:   Invoice[];
  documents:  Document[];
  accounting: AccountingRecord[];
}

// ── Create / Update payload shapes ───────────────────────────
export type ClientCreatePayload = Omit<Client, "id" | "avatar" | "lastActivity">;
export type ClientUpdatePayload = Partial<ClientCreatePayload>;

// ── Service ───────────────────────────────────────────────────
export const clientService = {
  /** Fetch all clients (workspace list). */
  async getAll(params: GetClientsParams = {}): Promise<PaginatedClients> {
    const qs = new URLSearchParams();
    if (params.page)       qs.set("page",       String(params.page));
    if (params.page_size)  qs.set("page_size",  String(params.page_size));
    if (params.search)     qs.set("search",     params.search);
    if (params.sort_by)    qs.set("sort_by",    params.sort_by);
    if (params.sort_order) qs.set("sort_order", params.sort_order);
    if (params.status     && params.status     !== "all") qs.set("status",     params.status);
    if (params.risk_level && params.risk_level !== "all") qs.set("risk_level", params.risk_level);
    const q = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<PaginatedClients>(`/clients${q}`);
  },

  /** Full client dashboard — called when a workspace card is clicked. */
  async getDashboard(dbId: string): Promise<ClientDashboard> {
    return api.get<ClientDashboard>(`/clients/${dbId}`);
  },

  /** Create a new client from the Add Client form. */
  async create(payload: ClientCreatePayload): Promise<ClientCard> {
    return api.post<ClientCard>("/clients", payload);
  },

  /** Partial update of an existing client. */
  async update(dbId: string, payload: ClientUpdatePayload): Promise<ClientCard> {
    return api.put<ClientCard>(`/clients/${dbId}`, payload);
  },

  /** Soft-delete a client. */
  async delete(dbId: string): Promise<{ message: string }> {
    return api.delete<{ message: string }>(`/clients/${dbId}`);
  },
};

export default clientService;
