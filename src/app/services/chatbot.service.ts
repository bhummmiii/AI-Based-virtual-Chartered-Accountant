/**
 * chatbot.service.ts
 * ──────────────────
 * Wraps the backend /api/v1/chatbot/* endpoints.
 * Uses the shared api.ts fetch client (auto-attaches Bearer token).
 *
 * Safety contract:
 *   - All AI responses must originate from backend-verified data.
 *   - client_id (UUID) must always be passed for client-scoped requests.
 *   - No hardcoded financial figures are ever generated client-side.
 */

import api from "./api";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChatRequest {
  message: string;
  session_id?: string;
  client_context?: string;
  client_id?: string;
}

export interface SourceItem {
  title: string;
  source: string;
  link?: string;
  client_code?: string;
  available?: boolean;
}

export interface ClientContextMeta {
  id: string;
  code: string;
  name: string;
  gstin?: string;
  risk?: string;
}

export interface ChatResponse {
  reply: string;
  session_id: string;
  sources?: SourceItem[];
  client_context?: ClientContextMeta;
  data_available?: boolean;
}

export interface ChatbotStatus {
  ready: boolean;
  model: string;
  message: string;
}

/** Contextual chat: client_id + period enriches the prompt via the backend context builder. */
export interface ContextualChatRequest {
  message: string;
  session_id?: string;
  client_id?: string;   // UUID
  period?: string;      // e.g. "2026-07" or "Q2 FY 2026-27"
}

/** A single AI insight card — always sourced from backend data. */
export interface AIInsightItem {
  id: number;
  text: string;
  /** "danger" | "warning" | "success" | "info" */
  severity: "danger" | "warning" | "success" | "info";
  source: "backend";
}

export interface AIInsightsResponse {
  client_id: string;
  client_name: string;
  period: string | null;
  insights: AIInsightItem[];
  data_available: boolean;
  message: string;
}

export interface ClientMatch {
  client_id: string;
  name: string;
  gstin: string | null;
  client_code: string;
}

export interface ClientResolveResponse {
  matches: ClientMatch[];
  ambiguous: boolean;
  message: string;
}

// ── Service ───────────────────────────────────────────────────────────────────

export const chatbotService = {
  /**
   * Send a user message and receive an AI reply.
   * Pass session_id to continue a multi-turn conversation.
   */
  async send(request: ChatRequest): Promise<ChatResponse> {
    return api.post<ChatResponse>("/chatbot/chat", request);
  },

  /**
   * Send a message enriched with real, backend-verified client context.
   * Always use this for client-workspace conversations.
   *
   * @param request.client_id  UUID of the client (never mix clients)
   * @param request.period     Optional period string (e.g. "2026-07")
   */
  async sendWithContext(request: ContextualChatRequest): Promise<ChatResponse> {
    return api.post<ChatResponse>("/chatbot/chat-with-context", request);
  },

  /**
   * Fetch real, backend-grounded AI insights for a specific client.
   * These replace the hardcoded `aiSuggestions` mock array.
   *
   * @param clientId  UUID of the target client
   * @param period    Optional filing period
   */
  async getClientInsights(clientId: string, period?: string): Promise<AIInsightsResponse> {
    const params = period ? `?period=${encodeURIComponent(period)}` : "";
    return api.get<AIInsightsResponse>(`/chatbot/insights/${clientId}${params}`);
  },

  /**
   * Resolve a partial client name or GSTIN to a client_id.
   * If ambiguous, caller must ask the user to clarify.
   */
  async resolveClient(query: string): Promise<ClientResolveResponse> {
    return api.get<ClientResolveResponse>(
      `/chatbot/resolve-client?q=${encodeURIComponent(query)}`
    );
  },

  /**
   * Pre-create a new session (optional — the /chat endpoint does this
   * automatically when no session_id is supplied).
   */
  async newSession(): Promise<string> {
    const { session_id } = await api.get<{ session_id: string }>("/chatbot/session/new");
    return session_id;
  },

  /**
   * Clear conversation history for a session on the server.
   */
  async clearSession(sessionId: string): Promise<void> {
    await api.delete<void>(`/chatbot/session/${sessionId}`);
  },

  /**
   * Check whether the Gemini API is configured and ready.
   */
  async getStatus(): Promise<ChatbotStatus> {
    return api.get<ChatbotStatus>("/chatbot/status");
  },
};

export default chatbotService;
