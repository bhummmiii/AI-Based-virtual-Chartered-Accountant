/**
 * api.ts — Base HTTP client for the CA Assistant backend.
 *
 * Uses the native fetch API (no axios required).
 * Base URL is read from VITE_API_BASE_URL env variable.
 * JWT token is stored in localStorage under "ca_token".
 *
 * All requests automatically attach the Bearer token.
 * All responses are unwrapped from the { success, data, message } envelope.
 */

const BASE_URL = (import.meta.env.VITE_API_BASE_URL as string) ?? "http://localhost:8000/api/v1";

// ── Token helpers ─────────────────────────────────────────────
export const getToken = (): string | null => localStorage.getItem("ca_token");
export const setToken = (token: string): void => localStorage.setItem("ca_token", token);
export const clearToken = (): void => localStorage.removeItem("ca_token");

// ── API Error class ───────────────────────────────────────────
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

// ── Core fetch wrapper ────────────────────────────────────────
async function request<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getToken();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  });

  // Parse JSON body regardless of status so we can read error messages
  const body = await response.json().catch(() => ({}));

  if (!response.ok) {
    // FastAPI 422 returns detail as an array of {loc, msg, type} objects
    // All other errors return detail as a string
    let message: string;
    if (Array.isArray(body?.detail)) {
      // Extract the human-readable msg from each validation error
      message = body.detail
        .map((e: { loc?: string[]; msg?: string }) =>
          e.loc ? `${e.loc.slice(1).join(".")}: ${e.msg}` : e.msg ?? "Validation error"
        )
        .join(" | ");
    } else {
      message =
        body?.detail ??
        body?.message ??
        `Request failed with status ${response.status}`;
    }
    throw new ApiError(response.status, String(message), body);
  }

  // Backend wraps every response in { success, data, message }
  // Return the inner data directly
  return (body?.data ?? body) as T;
}

// ── Convenience wrappers ──────────────────────────────────────
export const api = {
  get: <T>(path: string) =>
    request<T>(path, { method: "GET" }),

  post: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  put: <T>(path: string, body: unknown) =>
    request<T>(path, {
      method: "PUT",
      body: JSON.stringify(body),
    }),

  delete: <T>(path: string) =>
    request<T>(path, { method: "DELETE" }),
};

export default api;
