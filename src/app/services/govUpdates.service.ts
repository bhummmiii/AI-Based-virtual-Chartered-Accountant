import { api } from "./api";

export interface GovSource {
  id: string;
  code: string;
  name: string;
  base_url: string;
  domain: string;
  tier: number;
  scope: string;
  state_code?: string | null;
  method: string;
  enabled: boolean;
  status: "ok" | "degraded" | "blocked_requires_verification" | "unreachable" | "disabled";
  robots_ok: boolean;
  captcha_detected: boolean;
  tos_note?: string | null;
  crawl_delay_seconds: number;
  last_run_at?: string | null;
  last_attempt_at?: string | null;
  last_success_at?: string | null;
  consecutive_failures?: number;
  failure_stage?: string | null;
  last_error?: string | null;
  next_retry_at?: string | null;
  last_probe_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface GovUpdateAiSummary {
  summary: string;
  who_is_affected: string;
  key_dates: string[];
  action_items: string[];
  disclaimer?: string;
}

export interface GovUpdate {
  id: string;
  source_id: string;
  source_name?: string | null;
  source_code?: string | null;
  source_domain?: string | null;
  title: string;
  doc_type: string;
  legal_status: string;
  doc_number?: string | null;
  doc_number_source?: string | null;
  issue_date?: string | null;
  issue_date_source?: string | null;
  date_precision?: string;
  effective_date?: string | null;
  category: string;
  topics: string[];
  law_version?: string | null;
  url: string;
  link_quality?: string;
  ministry?: string | null;
  pdf_url?: string | null;
  content_text?: string | null;
  text_status: string;
  status: string;
  status_confidence?: number | null;
  supersedes_refs: string[];
  hidden?: boolean;
  hidden_reason?: string | null;
  is_manual?: boolean;
  manual_added_at?: string | null;
  first_seen_at: string;
  fetched_at: string;
  updated_at: string;
  backfilled: boolean;
  is_new: boolean;
  is_saved: boolean;
  ai_summary?: GovUpdateAiSummary | null;
  ai_status?: string | null;
}

export interface GovUpdatesListResponse {
  items: GovUpdate[];
  total: number;
  page: number;
  page_size: number;
  facets: {
    categories: Record<string, number>;
    doc_types: Record<string, number>;
    law_versions: Record<string, number>;
    statuses: Record<string, number>;
  };
}

export interface GovCategorySourceItem {
  code: string;
  name: string;
  status: string;
  enabled: boolean;
  last_error?: string | null;
}

export interface GovMetaResponse {
  category_counts: Record<string, number>;
  total_updates: number;
  last_sync_at?: string | null;
  last_attempt_at?: string | null;
  sources_total: number;
  sources_ok: number;
  sources_degraded: number;
  sources_blocked: number;
  sources_unreachable: number;
  sources_disabled: number;
  category_sources?: Record<string, GovCategorySourceItem[]>;
}

export interface GovUpdatesFilterParams {
  category?: string;
  source?: string;
  doc_type?: string;
  law_version?: string;
  topic?: string;
  status?: string;
  legal_status?: string;
  date_from?: string;
  date_to?: string;
  q?: string;
  saved?: boolean;
  include_archive?: boolean;
  show_administrative?: boolean;
  show_hidden?: boolean;
  page?: number;
  page_size?: number;
}

export const govUpdatesService = {
  async getUpdates(params: GovUpdatesFilterParams = {}): Promise<GovUpdatesListResponse> {
    const searchParams = new URLSearchParams();
    if (params.category) searchParams.set("category", params.category);
    if (params.source) searchParams.set("source", params.source);
    if (params.doc_type) searchParams.set("doc_type", params.doc_type);
    if (params.law_version) searchParams.set("law_version", params.law_version);
    if (params.topic) searchParams.set("topic", params.topic);
    if (params.status) searchParams.set("status", params.status);
    if (params.legal_status) searchParams.set("legal_status", params.legal_status);
    if (params.date_from) searchParams.set("date_from", params.date_from);
    if (params.date_to) searchParams.set("date_to", params.date_to);
    if (params.q) searchParams.set("q", params.q);
    if (params.saved) searchParams.set("saved", "true");
    if (params.include_archive !== undefined) searchParams.set("include_archive", String(params.include_archive));
    if (params.show_administrative !== undefined) searchParams.set("show_administrative", String(params.show_administrative));
    if (params.show_hidden !== undefined) searchParams.set("show_hidden", String(params.show_hidden));
    if (params.page) searchParams.set("page", String(params.page));
    if (params.page_size) searchParams.set("page_size", String(params.page_size));

    const qs = searchParams.toString();
    return api.get<GovUpdatesListResponse>(`/gov-updates${qs ? `?${qs}` : ""}`);
  },

  async getUpdateById(id: string): Promise<GovUpdate> {
    return api.get<GovUpdate>(`/gov-updates/${id}`);
  },

  async saveUpdate(id: string): Promise<{ status: string; update_id: string }> {
    return api.post<{ status: string; update_id: string }>(`/gov-updates/${id}/save`, {});
  },

  async unsaveUpdate(id: string): Promise<{ status: string; update_id: string }> {
    return api.delete<{ status: string; update_id: string }>(`/gov-updates/${id}/save`);
  },

  async getMeta(): Promise<GovMetaResponse> {
    return api.get<GovMetaResponse>("/gov-updates/meta");
  },

  async getSources(): Promise<GovSource[]> {
    return api.get<GovSource[]>("/gov-updates/sources");
  },

  async toggleSource(id: string, enabled: boolean): Promise<GovSource> {
    return api.patch<GovSource>(`/gov-updates/sources/${id}`, { enabled });
  },

  async reprobeSource(id: string): Promise<GovSource> {
    return api.post<GovSource>(`/gov-updates/sources/${id}/reprobe`, {});
  },

  async manualImport(formData: FormData): Promise<GovUpdate> {
    return api.post<GovUpdate>("/gov-updates/manual-import", formData, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },

  async triggerSync(source_code?: string, backfill: boolean = false): Promise<unknown> {
    return api.post<unknown>("/gov-updates/sync", { source_code, backfill });
  },
};
