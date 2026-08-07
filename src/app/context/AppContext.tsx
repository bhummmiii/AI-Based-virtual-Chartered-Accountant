/**
 * AppContext.tsx — Global application state backed by the FastAPI backend.
 * db_id is now a UUID string matching the PostgreSQL UUID primary key.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  ReactNode,
} from "react";
import { toast } from "sonner";
import { type Client } from "../data/mock";
import { clientService, type ClientCard } from "../services/client.service";
import { getToken } from "../services/api";

// ── Context shape ─────────────────────────────────────────────
type AppState = {
  theme: "light" | "dark";
  toggleTheme: () => void;
  clients: Client[];
  loading: boolean;
  error: string | null;
  getClient: (id: string) => Client | undefined;
  refreshClients: () => Promise<void>;
  addClient: (c: Omit<Client, "id" | "avatar" | "lastActivity" | "audit" | "tax">) => Promise<void>;
  updateClient: (id: string, c: Partial<Client>) => Promise<void>;
  deleteClient: (id: string) => Promise<void>;
};

const AppContext = createContext<AppState | null>(null);

// ── Helpers ────────────────────────────────────────────────────
const initials = (company: string) =>
  company
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

/** Map a backend ClientCard to the frontend Client type. */
function toClient(card: ClientCard): Client {
  return {
    id: card.id,                  // client_code, e.g. "C-1042"
    name: card.name,              // contact_person
    company: card.company,        // company_name
    type: card.type as Client["type"],
    gstin: card.gstin ?? "",
    revenue: card.revenue ?? 0,
    status: card.status as Client["status"],
    gst: card.gst as Client["gst"],
    audit: card.audit as Client["audit"],
    tax: card.tax as Client["tax"],
    risk: card.risk as Client["risk"],
    lastActivity: card.lastActivity ?? "Recently",
    avatar: card.avatar ?? initials(card.company),
  };
}

// ── Provider ───────────────────────────────────────────────────
export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("fl_theme") as "light" | "dark") || "light",
  );
  const [clients, setClients] = useState<Client[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [tokenReady, setTokenReady] = useState(() => !!localStorage.getItem("ca_token"));

  // ── Theme ──
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("fl_theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  // ── Load clients from backend ──────────────────────────────
  const refreshClients = useCallback(async () => {
    if (!localStorage.getItem("ca_token")) {
      setClients([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await clientService.getAll({ page_size: 200 });
      result.items.forEach((card) => {
        dbIdMap.set(card.id, card.db_id);
      });
      setClients(result.items.map(toClient));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load clients";
      setError(msg);
      console.error("[AppContext] Failed to load clients:", err);
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-check token on storage changes (fires after login sets the token)
  useEffect(() => {
    const handleStorage = () => {
      const hasToken = !!localStorage.getItem("ca_token");
      setTokenReady(hasToken);
    };
    window.addEventListener("storage", handleStorage);
    return () => window.removeEventListener("storage", handleStorage);
  }, []);

  // Fetch clients whenever token becomes available
  useEffect(() => {
    refreshClients();
  }, [refreshClients, tokenReady]);

  // ── Lookup ──────────────────────────────────────────────────
  const getClient = (id: string) => clients.find((c) => c.id === id);

  // ── Add client ─────────────────────────────────────────────
  const addClient = async (c: Omit<Client, "id" | "avatar" | "lastActivity" | "audit" | "tax">) => {
    try {
      const card = await clientService.create(c);
      const newClient = toClient(card);
      dbIdMap.set(card.id, card.db_id);
      setClients((prev) => [newClient, ...prev]);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create client";
      toast.error("Failed to add client", { description: msg });
      throw err;
    }
  };

  // ── Update client ──────────────────────────────────────────
  const updateClient = async (id: string, patch: Partial<Client>) => {
    // Find the db_id by locating the matching client in our state
    // We stored it nowhere — so we need to retrieve it from the backend.
    // Strategy: find client by client_code (id), use the db_id from the
    // ClientCard that was stored when we loaded. We keep a parallel map.
    // Simpler approach: the backend also accepts client_code lookup via
    // the existing integer PK. We'll fetch the current clients list to
    // find the db_id, or we store db_id on the Client object.
    //
    // Best solution: we keep a local map of client_code → db_id.
    const dbId = dbIdMap.get(id);
    if (!dbId) {
      toast.error("Update failed", { description: "Client not found in local state" });
      return;
    }
    try {
      const card = await clientService.update(dbId, patch);
      const updated = toClient(card);
      setClients((prev) => prev.map((c) => (c.id === id ? updated : c)));
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to update client";
      toast.error("Update failed", { description: msg });
      throw err;
    }
  };

  // ── Delete client ──────────────────────────────────────────
  const deleteClient = async (id: string) => {
    const dbId = dbIdMap.get(id);
    if (!dbId) {
      // Optimistic local remove even if we can't find db_id
      setClients((prev) => prev.filter((c) => c.id !== id));
      return;
    }
    try {
      await clientService.delete(dbId);
      setClients((prev) => prev.filter((c) => c.id !== id));
      dbIdMap.delete(id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete client";
      toast.error("Delete failed", { description: msg });
      throw err;
    }
  };

  return (
    <AppContext.Provider
      value={{
        theme,
        toggleTheme,
        clients,
        loading,
        error,
        getClient,
        refreshClients,
        addClient,
        updateClient,
        deleteClient,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error("useApp must be used within AppProvider");
  return ctx;
}

/**
 * Module-level map: client_code (e.g. "CLI-001") → UUID string.
 * Populated when clients are fetched. Used for PUT/DELETE/dashboard calls.
 */
export const dbIdMap = new Map<string, string>();
