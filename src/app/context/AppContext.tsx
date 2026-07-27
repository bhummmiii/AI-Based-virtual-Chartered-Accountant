import { createContext, useContext, useEffect, useState, ReactNode } from "react";
import { clients as seedClients, type Client } from "../data/mock";

type AppState = {
  theme: "light" | "dark";
  toggleTheme: () => void;
  clients: Client[];
  getClient: (id: string) => Client | undefined;
  addClient: (c: Omit<Client, "id" | "avatar" | "lastActivity">) => void;
  updateClient: (id: string, c: Partial<Client>) => void;
  deleteClient: (id: string) => void;
};

const AppContext = createContext<AppState | null>(null);

const initials = (company: string) =>
  company
    .split(" ")
    .map((w) => w[0])
    .join("")
    .slice(0, 2)
    .toUpperCase();

export function AppProvider({ children }: { children: ReactNode }) {
  const [theme, setTheme] = useState<"light" | "dark">(
    () => (localStorage.getItem("fl_theme") as "light" | "dark") || "light",
  );
  const [clients, setClients] = useState<Client[]>(seedClients);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem("fl_theme", theme);
  }, [theme]);

  const toggleTheme = () => setTheme((t) => (t === "dark" ? "light" : "dark"));

  const getClient = (id: string) => clients.find((c) => c.id === id);

  const addClient: AppState["addClient"] = (c) => {
    const nextNum = 1042 + clients.length;
    const newClient: Client = {
      ...c,
      id: `C-${nextNum}`,
      avatar: initials(c.company),
      lastActivity: "Just now",
    };
    setClients((prev) => [newClient, ...prev]);
  };

  const updateClient: AppState["updateClient"] = (id, patch) =>
    setClients((prev) => prev.map((c) => (c.id === id ? { ...c, ...patch } : c)));

  const deleteClient: AppState["deleteClient"] = (id) =>
    setClients((prev) => prev.filter((c) => c.id !== id));

  return (
    <AppContext.Provider
      value={{ theme, toggleTheme, clients, getClient, addClient, updateClient, deleteClient }}
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
