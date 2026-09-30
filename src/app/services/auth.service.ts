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

export interface GoogleAuthPayload {
  email: string;
  password?: string;
  name?: string;
  google_id?: string;
  avatar_url?: string;
}

// ── User State Helpers ──────────────────────────────────────────
export interface StoredUser {
  id?: string | number;
  full_name: string;
  email: string;
  role: string;
  initials: string;
  firstName: string;
  lastName: string;
}

export interface RecentAccount {
  name: string;
  email: string;
  hasPasswordSet?: boolean;
}

export function getStoredUser(): StoredUser {
  let full_name = "Mahendra Pawar";
  let email = "Mahendrapawar@gmail.com";
  let role = "ca";

  try {
    const raw = localStorage.getItem("ca_user");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (parsed.full_name || parsed.name) {
        full_name = parsed.full_name || parsed.name;
      }
      if (parsed.email) {
        email = parsed.email;
      }
      if (parsed.role) {
        role = parsed.role;
      }
    }
  } catch {}

  const parts = full_name.trim().split(/\s+/);
  const firstName = parts[0] || "CA";
  const lastName = parts.length > 1 ? parts.slice(1).join(" ") : "";
  const initials =
    parts.length >= 2
      ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
      : full_name.slice(0, 2).toUpperCase();

  return { full_name, email, role, initials, firstName, lastName };
}

export function getUserInitials(name: string): string {
  if (!name) return "MP";
  const parts = name.trim().split(/\s+/);
  if (parts.length >= 2) {
    return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
  }
  return name.slice(0, 2).toUpperCase();
}

export function getRecentAccounts(): RecentAccount[] {
  try {
    const raw = localStorage.getItem("ca_accounts");
    if (raw) {
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed) && parsed.length > 0) {
        return parsed.map((a: any) => ({
          name: a.name || a.email.split("@")[0],
          email: a.email,
          hasPasswordSet: a.hasPasswordSet ?? true,
        }));
      }
    }
  } catch {}
  // Default to Mahendra Pawar (already authenticated with password)
  return [{ name: "Mahendra Pawar", email: "Mahendrapawar@gmail.com", hasPasswordSet: true }];
}

export function saveRecentAccount(name: string, email: string, hasPasswordSet = true) {
  try {
    const accounts = getRecentAccounts();
    const filtered = accounts.filter(
      (a) => a.email.toLowerCase() !== email.toLowerCase()
    );
    filtered.unshift({ name, email, hasPasswordSet });
    localStorage.setItem("ca_accounts", JSON.stringify(filtered.slice(0, 5)));
  } catch {}
}

export function isAccountRemembered(email: string): boolean {
  if (!email) return false;
  try {
    const accounts = getRecentAccounts();
    const found = accounts.find(
      (a) => a.email.toLowerCase() === email.trim().toLowerCase()
    );
    return !!found?.hasPasswordSet;
  } catch {
    return false;
  }
}

function persistUser(user: any) {
  if (!user) return;
  const full_name = user.full_name || user.name || (user.email ? user.email.split("@")[0] : "Mahendra Pawar");
  const email = user.email || "Mahendrapawar@gmail.com";
  const role = user.role || "ca";
  const userToSave = { full_name, email, role };
  localStorage.setItem("ca_user", JSON.stringify(userToSave));
  saveRecentAccount(full_name, email, true);
}

// ── Service ────────────────────────────────────────────────────
export const authService = {
  async login(payload: LoginPayload): Promise<TokenResponse> {
    const result = await api.post<TokenResponse>("/auth/login", payload);
    setToken(result.access_token);
    if (result.user) {
      persistUser(result.user);
    }
    return result;
  },

  async register(payload: RegisterPayload): Promise<TokenResponse> {
    const result = await api.post<TokenResponse>("/auth/register", payload);
    setToken(result.access_token);
    if (result.user) {
      persistUser(result.user);
    } else {
      persistUser({ full_name: payload.name, email: payload.email, role: payload.role || "ca" });
    }
    return result;
  },

  async googleAuth(payload: GoogleAuthPayload): Promise<TokenResponse> {
    const result = await api.post<TokenResponse>("/auth/google", payload);
    setToken(result.access_token);
    if (result.user) {
      persistUser(result.user);
    } else {
      persistUser({ full_name: payload.name || payload.email.split("@")[0], email: payload.email, role: "ca" });
    }
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
