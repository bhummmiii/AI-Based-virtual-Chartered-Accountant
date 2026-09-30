/**
 * chatbot.service.ts
 * ──────────────────
 * Wraps the backend /api/v1/chatbot/* endpoints.
 * Uses the shared api.ts fetch client (auto-attaches Bearer token).
 */

import api from "./api";

// ── Types ─────────────────────────────────────────────────────────────────────

export interface ChatRequest {
  message: string;
  session_id?: string;
  client_context?: string;
}

export interface ChatResponse {
  reply: string;
  session_id: string;
}

export interface ChatbotStatus {
  ready: boolean;
  model: string;
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
