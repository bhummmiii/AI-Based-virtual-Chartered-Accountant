import { useState, useEffect, useMemo } from "react";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  FolderKanban,
  Sparkles,
  Landmark,
  FileBarChart,
  Bell,
  Settings,
  Search,
  Menu,
  LogOut,
  ChevronDown,
  Sun,
  Moon,
} from "lucide-react";
import { Input } from "../ui/input";
import { Avatar, AvatarFallback } from "../ui/avatar";
import { GlobalSearch } from "../common/GlobalSearch";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "../ui/dropdown-menu";
import { Sheet, SheetContent, SheetTrigger, SheetTitle } from "../ui/sheet";
import { Button } from "../ui/button";
import { cn } from "../ui/utils";
import { useApp } from "../../context/AppContext";
import { authService, getStoredUser } from "../../services/auth.service";

const nav = [
  {
    section: "Menu",
    items: [
      { to: "/app", label: "Dashboard", icon: LayoutDashboard, end: true },
      { to: "/app/workspace", label: "Workspace", icon: FolderKanban },
      { to: "/app/assistant", label: "AI Assistant", icon: Sparkles },
      { to: "/app/updates", label: "Government Updates", icon: Landmark },
      { to: "/app/reports", label: "Reports", icon: FileBarChart },
      { to: "/app/settings", label: "Settings", icon: Settings },
    ],
  },
];

function Brand() {
  return (
    <div className="flex items-center gap-2.5 px-2">
      <div className="flex size-9 items-center justify-center rounded-xl bg-primary text-primary-foreground">
        <span className="text-sm tracking-tight">CA</span>
      </div>
      <div className="leading-tight">
        <p className="text-sm">FinLedger AI</p>
        <p className="text-muted-foreground text-xs">CA Assistant</p>
      </div>
    </div>
  );
}

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  return (
    <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
      {nav.map((group) => (
        <div key={group.section} className="space-y-1">
          <p className="px-3 pb-1 text-xs uppercase tracking-wider text-muted-foreground">{group.section}</p>
          {group.items.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={(item as { end?: boolean }).end}
              onClick={onNavigate}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground hover:bg-secondary",
                )
              }
            >
              <item.icon className="size-4.5 shrink-0" />
              {item.label}
            </NavLink>
          ))}
        </div>
      ))}
    </nav>
  );
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const { theme, toggleTheme, refreshClients, clients } = useApp();
  const [currentUser, setCurrentUser] = useState(getStoredUser());

  // Derive notifications dynamically from the current CA's actual clients
  const dynamicNotifications = useMemo(() => {
    if (!clients || !clients.length) {
      return [
        { id: 1, title: "Workspace initialized", body: "Add your first client to start auditing and tracking filings.", time: "Just now", type: "info", unread: true },
        { id: 2, title: "New GST circular published", body: "Circular 214/8/2026 — e-invoicing threshold update.", time: "2d ago", type: "info", unread: false },
      ];
    }
    const dueClients = clients.filter((c) => c.gst === "Due" || c.gst === "Overdue");
    const flaggedClient = clients.find((c) => c.audit === "Flagged");
    const activeClient = clients.find((c) => c.status === "Active") || clients[0];

    const notifs = [];
    if (dueClients.length > 0) {
      notifs.push({
        id: 1,
        title: "GSTR-3B due in 5 days",
        body: `Filing due for ${dueClients.slice(0, 2).map((c) => c.company).join(", ")}${dueClients.length > 2 ? ` + ${dueClients.length - 2} more` : ""}.`,
        time: "2h ago",
        type: "warning",
        unread: true,
      });
    } else {
      notifs.push({
        id: 1,
        title: "All GST returns up-to-date",
        body: `All active clients currently filed for recent period.`,
        time: "2h ago",
        type: "success",
        unread: false,
      });
    }

    if (flaggedClient) {
      notifs.push({
        id: 2,
        title: "Audit flag raised",
        body: `${flaggedClient.company} — suspicious journal entries detected.`,
        time: "5h ago",
        type: "danger",
        unread: true,
      });
    } else {
      notifs.push({
        id: 2,
        title: "Audit health check passed",
        body: `Compliance verified for ${activeClient.company}.`,
        time: "5h ago",
        type: "success",
        unread: true,
      });
    }

    notifs.push({
      id: 3,
      title: "Invoice OCR complete",
      body: `12 invoices processed with 98% avg confidence for ${activeClient.company}.`,
      time: "1d ago",
      type: "success",
      unread: false,
    });

    notifs.push({
      id: 4,
      title: "New GST circular published",
      body: "Circular 214/8/2026 — e-invoicing threshold update.",
      time: "2d ago",
      type: "info",
      unread: false,
    });

    return notifs;
  }, [clients]);

  const unread = dynamicNotifications.filter((n) => n.unread).length;

  // Fetch clients and refresh user profile whenever authenticated shell mounts
  useEffect(() => {
    setCurrentUser(getStoredUser());
    refreshClients();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="flex h-screen w-full overflow-hidden bg-background text-foreground">
      {/* Desktop sidebar */}
      <aside className="hidden w-64 shrink-0 flex-col border-r border-sidebar-border bg-sidebar lg:flex">
        <div className="flex h-16 items-center border-b border-sidebar-border px-4">
          <Brand />
        </div>
        <NavItems />
        <div className="border-t border-sidebar-border p-3">
          <div className="rounded-lg bg-accent p-3">
            <p className="text-sm text-accent-foreground">Pro plan</p>
            <p className="text-muted-foreground text-xs">Unlimited AI audits & OCR</p>
            <Button size="sm" className="mt-2 w-full">Manage plan</Button>
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        {/* Topbar */}
        <header className="flex h-16 shrink-0 items-center gap-3 border-b border-border bg-card px-4 lg:px-6">
          <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
            <SheetTrigger asChild>
              <Button variant="ghost" size="icon" className="lg:hidden">
                <Menu className="size-5" />
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-72 p-0">
              <SheetTitle className="sr-only">Navigation</SheetTitle>
              <div className="flex h-16 items-center border-b border-sidebar-border px-4">
                <Brand />
              </div>
              <NavItems onNavigate={() => setMobileOpen(false)} />
            </SheetContent>
          </Sheet>

          <div className="hidden max-w-md flex-1 md:block">
            <GlobalSearch />
          </div>

          <div className="ml-auto flex items-center gap-1">
            <Button variant="ghost" size="icon" onClick={toggleTheme} aria-label="Toggle theme">
              {theme === "dark" ? <Sun className="size-5" /> : <Moon className="size-5" />}
            </Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="ghost" size="icon" className="relative">
                  <Bell className="size-5" />
                  {unread > 0 && (
                    <span className="absolute right-1.5 top-1.5 size-2 rounded-full bg-destructive ring-2 ring-card" />
                  )}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80">
                <DropdownMenuLabel className="flex items-center justify-between">
                  Notifications
                  {unread > 0 && <span className="text-xs text-muted-foreground">{unread} unread</span>}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {dynamicNotifications.map((n) => (
                  <DropdownMenuItem key={n.id} className="flex-col items-start gap-0.5 whitespace-normal py-2.5">
                    <div className="flex w-full items-center gap-2">
                      {n.unread && <span className="size-1.5 shrink-0 rounded-full bg-primary" />}
                      <span className="text-sm">{n.title}</span>
                    </div>
                    <span className="text-xs text-muted-foreground">{n.body}</span>
                    <span className="text-xs text-muted-foreground">{n.time}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-secondary">
                  <Avatar className="size-8">
                    <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">
                      {currentUser.initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="hidden text-left leading-tight sm:block">
                    <p className="text-sm font-medium text-foreground">{currentUser.full_name}</p>
                    <p className="text-muted-foreground text-xs">Chartered Accountant</p>
                  </div>
                  <ChevronDown className="hidden size-4 text-muted-foreground sm:block" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-60">
                <DropdownMenuLabel className="font-normal">
                  <div className="flex flex-col space-y-1">
                    <p className="text-sm font-semibold text-foreground">{currentUser.full_name}</p>
                    <p className="text-xs text-muted-foreground truncate">{currentUser.email}</p>
                    <span className="w-fit rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-medium text-primary">
                      Chartered Accountant
                    </span>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/app/settings")}>
                  <Settings className="size-4" /> Settings
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    authService.logout();
                    navigate("/");
                  }}
                >
                  <LogOut className="size-4" /> Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto max-w-[1400px] space-y-6 p-4 lg:p-6">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
