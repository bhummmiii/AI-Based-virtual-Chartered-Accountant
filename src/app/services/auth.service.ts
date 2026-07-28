/**
 * auth.service.ts — Authentication API calls.
 * Login, register. Stores and clears JWT tokens.
 */

import api, { setToken, clearToken } from "./api";
import type { Client } from "../data/mock";

// ── Types ─────────────────────────────────────────────────────
export interface UserResponse {
  id: number;
  name: string;
  email: string;
  role: string;
  created_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: UserResponse;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  name: string;
  email: string;
  password: string;
  role?: string;
}

// ── Service ────────────────────────────────────────────────────
export const authService = {
  async login(payload: LoginPayload): Promise<TokenResponse> {
    const result = await api.post<TokenResponse>("/auth/login", payload);
    setToken(result.access_token);
    return result;
  },

  async register(payload: RegisterPayload): Promise<TokenResponse> {
    const result = await api.post<TokenResponse>("/auth/register", payload);
    setToken(result.access_token);
    return result;
  },

  logout(): void {
    clearToken();
    localStorage.removeItem("ca_user");
  },

  isLoggedIn(): boolean {
    return !!localStorage.getItem("ca_token");
  },
};

export default authService;
