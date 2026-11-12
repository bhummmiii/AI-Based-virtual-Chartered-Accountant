/**
 * settings.service.ts — Service for managing user settings, profile, security,
 * notifications, preferences, and API keys.
 */

import api from "./api";

export interface FullSettings {
  id: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone?: string | null;
  role: string;
  membership_no: string;
  profile_image?: string | null;

  // Security settings
  two_factor_enabled: boolean;
  login_alerts: boolean;
  session_timeout_minutes: number;

  // Notification preferences
  compliance_deadlines: boolean;
  audit_alerts: boolean;
  client_activity: boolean;
  product_updates: boolean;

  // Preferences
  language: string;
  currency: string;
  theme: string;

  // API Key
  api_key: string;
  masked_key: string;
}

export interface ProfileUpdatePayload {
  first_name?: string;
  last_name?: string;
  email?: string;
  phone?: string;
  membership_no?: string;
  profile_image?: string | null;
}

export interface SecurityUpdatePayload {
  two_factor_enabled?: boolean;
  login_alerts?: boolean;
  session_timeout_minutes?: number;
}

export interface PasswordChangePayload {
  current_password: string;
  new_password: string;
}

export interface NotificationsUpdatePayload {
  compliance_deadlines?: boolean;
  audit_alerts?: boolean;
  client_activity?: boolean;
  product_updates?: boolean;
}

export interface PreferencesUpdatePayload {
  language?: string;
  currency?: string;
  theme?: string;
}

export interface ApiKeyData {
  api_key: string;
  masked_key: string;
  created_at?: string;
}

export const settingsService = {
  /**
   * Fetch complete settings and profile info for currently logged-in user.
   */
  async getSettings(): Promise<FullSettings> {
    return api.get<FullSettings>("/settings");
  },

  /**
   * Update profile information (first/last name, email, phone, membership number, photo).
   */
  async updateProfile(payload: ProfileUpdatePayload): Promise<FullSettings> {
    return api.put<FullSettings>("/settings/profile", payload);
  },

  /**
   * Update security settings (2FA, login alerts, session timeout).
   */
  async updateSecurity(payload: SecurityUpdatePayload): Promise<FullSettings> {
    return api.put<FullSettings>("/settings/security", payload);
  },

  /**
   * Change user password.
   */
  async changePassword(payload: PasswordChangePayload): Promise<{ success: boolean }> {
    return api.post<{ success: boolean }>("/settings/change-password", payload);
  },

  /**
   * Update notification preferences.
   */
  async updateNotifications(payload: NotificationsUpdatePayload): Promise<FullSettings> {
    return api.put<FullSettings>("/settings/notifications", payload);
  },

  /**
   * Update interface preferences (language, currency, theme).
   */
  async updatePreferences(payload: PreferencesUpdatePayload): Promise<FullSettings> {
    return api.put<FullSettings>("/settings/preferences", payload);
  },

  /**
   * Generate a brand-new live API key (revoking previous key).
   */
  async generateApiKey(): Promise<ApiKeyData> {
    return api.post<ApiKeyData>("/settings/api-key/generate", {});
  },
};

export default settingsService;
