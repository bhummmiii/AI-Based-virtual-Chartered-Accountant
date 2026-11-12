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
  CheckCheck,
  Clock,
  ArrowRight,
} from "lucide-react";
import { Input } from "../ui/input";
import { Avatar, AvatarFallback, AvatarImage } from "../ui/avatar";
import { GlobalSearch } from "../common/GlobalSearch";
import notificationService, { AppNotification } from "../../services/notification.service";
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
import { useTranslation } from "../../context/LanguageContext";
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
  const { t } = useTranslation();
  const navItems = [
    { to: "/app", label: t("nav.dashboard"), icon: LayoutDashboard, end: true },
    { to: "/app/workspace", label: t("nav.workspace"), icon: FolderKanban },
    { to: "/app/assistant", label: t("nav.assistant"), icon: Sparkles },
    { to: "/app/updates", label: t("nav.updates"), icon: Landmark },
    { to: "/app/reports", label: t("nav.reports"), icon: FileBarChart },
    { to: "/app/settings", label: t("nav.settings"), icon: Settings },
  ];

  return (
    <nav className="flex-1 space-y-6 overflow-y-auto px-3 py-4">
      <div className="space-y-1">
        <p className="px-3 pb-1 text-xs uppercase tracking-wider text-muted-foreground">{t("nav.menu")}</p>
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
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
    </nav>
  );
}

function formatRelativeTime(dateString?: string): string {
  if (!dateString) return "Just now";
  try {
    const now = Date.now();
    const date = new Date(dateString).getTime();
    if (isNaN(date)) return "Recently";
    const diffSec = Math.max(0, Math.floor((now - date) / 1000));
    if (diffSec < 60) return "Just now";
    const diffMin = Math.floor(diffSec / 60);
    if (diffMin < 60) return `${diffMin}m ago`;
    const diffHours = Math.floor(diffMin / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    const diffDays = Math.floor(diffHours / 24);
    return `${diffDays}d ago`;
  } catch {
    return "Recently";
  }
}

export function AppLayout() {
  const [mobileOpen, setMobileOpen] = useState(false);
  const navigate = useNavigate();
  const { theme, toggleTheme, refreshClients, clients } = useApp();
  const { t } = useTranslation();
  const [currentUser, setCurrentUser] = useState(getStoredUser());

  // ── Live Notifications State ────────────────────────────────
  const [notifications, setNotifications] = useState<AppNotification[]>([]);
  const [unreadCount, setUnreadCount] = useState<number>(0);

  const fetchLiveNotifications = async () => {
    try {
      const data = await notificationService.getNotifications();
      if (data && data.notifications) {
        setNotifications(data.notifications);
        setUnreadCount(
          data.unread_count ?? data.notifications.filter((n) => !n.is_read).length
        );
      }
    } catch (e) {
      console.warn("Error fetching live notifications:", e);
    }
  };

  const handleNotificationClick = async (notif: AppNotification) => {
    // 1. Mark as read immediately in local state
    if (!notif.is_read) {
      setNotifications((prev) =>
        prev.map((n) => (n.id === notif.id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
      try {
        await notificationService.markAsRead(notif.id);
      } catch (err) {
        console.warn("Failed to mark notification read:", err);
      }
    }

    // 2. Navigate immediately to linked section if present
    if (notif.link) {
      navigate(notif.link);
    }
  };

  const handleMarkAllRead = async (e: React.MouseEvent) => {
    e.stopPropagation();
    e.preventDefault();
    setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    setUnreadCount(0);
    try {
      await notificationService.markAllAsRead();
    } catch (err) {
      console.warn("Failed to mark all notifications read:", err);
    }
  };

  // Fetch clients, refresh user profile, and start real-time notification sync
  useEffect(() => {
    setCurrentUser(getStoredUser());
    refreshClients();
    fetchLiveNotifications();

    // Real-time polling every 15 seconds
    const timer = setInterval(fetchLiveNotifications, 15000);

    // Instant update on custom application events (upload, filing, verification)
    const handleUpdate = () => {
      fetchLiveNotifications();
    };
    window.addEventListener("finledger:notification-update", handleUpdate);

    // Sync user changes live across header without requiring full reload
    const handleUserUpdate = () => {
      setCurrentUser(getStoredUser());
    };
    window.addEventListener("ca_user_updated", handleUserUpdate);

    return () => {
      clearInterval(timer);
      window.removeEventListener("finledger:notification-update", handleUpdate);
      window.removeEventListener("ca_user_updated", handleUserUpdate);
    };
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
                <Button variant="ghost" size="icon" className="relative" aria-label="Notifications">
                  <Bell className="size-5" />
                  {unreadCount > 0 && (
                    <span className="absolute right-1.5 top-1.5 size-2.5 rounded-full bg-destructive ring-2 ring-card animate-pulse" />
                  )}
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-80 sm:w-96 max-h-[30rem] overflow-y-auto p-1 shadow-xl">
                <DropdownMenuLabel className="flex items-center justify-between py-2 px-3">
                  <div className="flex items-center gap-2">
                    <span className="font-semibold text-sm">Notifications</span>
                    {unreadCount > 0 && (
                      <span className="text-[11px] font-medium px-2 py-0.5 rounded-full bg-primary/10 text-primary">
                        {unreadCount} unread
                      </span>
                    )}
                  </div>
                  {unreadCount > 0 && (
                    <button
                      type="button"
                      onClick={handleMarkAllRead}
                      className="text-xs text-muted-foreground hover:text-primary transition-colors flex items-center gap-1 font-normal cursor-pointer"
                    >
                      <CheckCheck className="size-3.5" />
                      Mark all read
                    </button>
                  )}
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                {notifications.length === 0 ? (
                  <div className="py-8 text-center text-xs text-muted-foreground">
                    No notifications right now. You're all caught up!
                  </div>
                ) : (
                  notifications.map((n) => (
                    <DropdownMenuItem
                      key={n.id}
                      onClick={() => handleNotificationClick(n)}
                      className={cn(
                        "flex flex-col items-start gap-1 py-3 px-3 cursor-pointer transition-colors border-b border-border/40 last:border-b-0 outline-none",
                        !n.is_read ? "bg-muted/40 hover:bg-muted/70" : "hover:bg-muted/30 opacity-80 hover:opacity-100"
                      )}
                    >
                      <div className="flex w-full items-start justify-between gap-2">
                        <div className="flex items-center gap-2 min-w-0">
                          <span
                            className={cn(
                              "size-2 shrink-0 rounded-full",
                              !n.is_read
                                ? n.severity === "danger"
                                  ? "bg-rose-500 shadow-sm shadow-rose-500/50"
                                  : n.severity === "warning"
                                  ? "bg-amber-500 shadow-sm shadow-amber-500/50"
                                  : n.severity === "success"
                                  ? "bg-emerald-500 shadow-sm shadow-emerald-500/50"
                                  : "bg-primary shadow-sm shadow-primary/50"
                                : "bg-muted-foreground/30"
                            )}
                          />
                          <span
                            className={cn(
                              "text-xs truncate font-medium",
                              !n.is_read ? "text-foreground font-semibold" : "text-muted-foreground"
                            )}
                          >
                            {n.title}
                          </span>
                        </div>
                        <span className="text-[10px] text-muted-foreground shrink-0 flex items-center gap-1 font-mono">
                          <Clock className="size-3" />
                          {formatRelativeTime(n.created_at)}
                        </span>
                      </div>
                      <span className="text-xs text-muted-foreground/90 pl-4 line-clamp-2 leading-relaxed">
                        {n.message}
                      </span>
                      {n.link && (
                        <div className="flex items-center gap-1 text-[11px] text-primary/80 hover:text-primary pl-4 mt-0.5 font-medium">
                          <span>View section</span>
                          <ArrowRight className="size-3" />
                        </div>
                      )}
                    </DropdownMenuItem>
                  ))
                )}
              </DropdownMenuContent>
            </DropdownMenu>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="flex items-center gap-2 rounded-lg px-2 py-1.5 hover:bg-secondary">
                  <Avatar className="size-8">
                    {currentUser.profile_image && (
                      <AvatarImage src={currentUser.profile_image} alt={currentUser.full_name} />
                    )}
                    <AvatarFallback className="bg-primary text-primary-foreground text-xs font-semibold">
                      {currentUser.initials}
                    </AvatarFallback>
                  </Avatar>
                  <div className="hidden text-left leading-tight sm:block">
                    <p className="text-sm font-medium text-foreground">{currentUser.full_name}</p>
                    <p className="text-muted-foreground text-xs">{t("header.role")}</p>
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
                      {t("header.role")}
                    </span>
                  </div>
                </DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => navigate("/app/settings")}>
                  <Settings className="size-4" /> {t("nav.settings")}
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={() => {
                    authService.logout();
                    navigate("/");
                  }}
                >
                  <LogOut className="size-4" /> {t("header.sign_out")}
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
