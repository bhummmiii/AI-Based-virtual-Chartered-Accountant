import { useState, useEffect, useRef } from "react";
import {
  User,
  Shield,
  Bell,
  Palette,
  Eye,
  EyeOff,
  Sun,
  Moon,
  Loader2,
  Lock,
  Trash2,
} from "lucide-react";
import { toast } from "sonner";
import { PageHeader } from "../components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Avatar, AvatarFallback, AvatarImage } from "../components/ui/avatar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "../components/ui/dialog";
import { getStoredUser, saveRecentAccount } from "../services/auth.service";
import { settingsService } from "../services/settings.service";
import { useApp } from "../context/AppContext";
import { useTranslation, SupportedLanguage } from "../context/LanguageContext";

function Row({
  title,
  desc,
  children,
}: {
  title: string;
  desc: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div>
        <p className="text-sm font-medium">{title}</p>
        <p className="text-xs text-muted-foreground">{desc}</p>
      </div>
      {children}
    </div>
  );
}

export function Settings() {
  const { theme, setTheme } = useApp();
  const { t, language, setLanguage } = useTranslation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Global Settings State ─────────────────────────────────────
  const [loading, setLoading] = useState(true);
  const [savingProfile, setSavingProfile] = useState(false);
  const [updatingSecurity, setUpdatingSecurity] = useState(false);

  // ── Profile Fields ────────────────────────────────────────────
  const initialLocalUser = getStoredUser();
  const [firstName, setFirstName] = useState(initialLocalUser.firstName || "bhumi");
  const [lastName, setLastName] = useState(initialLocalUser.lastName || "jha");
  const [email, setEmail] = useState(initialLocalUser.email || "bhumi@gmail.com");
  const [membershipNo, setMembershipNo] = useState("ICAI-123456");
  const [profileImage, setProfileImage] = useState<string | null>(initialLocalUser.profile_image || null);

  // ── Security Fields ───────────────────────────────────────────
  const [twoFactor, setTwoFactor] = useState(true);
  const [loginAlerts, setLoginAlerts] = useState(true);
  const [sessionTimeout, setSessionTimeout] = useState(30);

  // ── Password Modal State ──────────────────────────────────────
  const [passwordDialogOpen, setPasswordDialogOpen] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [changingPassword, setChangingPassword] = useState(false);

  // ── Notification Preferences ──────────────────────────────────
  const [complianceDeadlines, setComplianceDeadlines] = useState(true);
  const [auditAlerts, setAuditAlerts] = useState(true);
  const [clientActivity, setClientActivity] = useState(false);
  const [productUpdates, setProductUpdates] = useState(true);

  // ── Load Settings from Backend ────────────────────────────────
  useEffect(() => {
    let isMounted = true;
    async function fetchSettings() {
      try {
        setLoading(true);
        const data = await settingsService.getSettings();
        if (!isMounted) return;

        // Profile
        if (data.first_name) setFirstName(data.first_name);
        if (data.last_name) setLastName(data.last_name);
        if (data.email) setEmail(data.email);
        if (data.membership_no) setMembershipNo(data.membership_no);
        if (data.profile_image) {
          setProfileImage(data.profile_image);
        }

        // Security
        setTwoFactor(data.two_factor_enabled);
        setLoginAlerts(data.login_alerts);
        setSessionTimeout(data.session_timeout_minutes || 30);

        // Notifications
        setComplianceDeadlines(data.compliance_deadlines);
        setAuditAlerts(data.audit_alerts);
        setClientActivity(data.client_activity);
        setProductUpdates(data.product_updates);

        // Preferences
        if (data.language && (data.language === "en" || data.language === "hi" || data.language === "gu" || data.language === "mr" || data.language === "ta")) {
          setLanguage(data.language as SupportedLanguage);
        }
        if (data.theme && (data.theme === "dark" || data.theme === "light")) {
          setTheme(data.theme);
        }
      } catch (err) {
        console.warn("[Settings] Using stored local settings fallback:", err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    fetchSettings();
    return () => {
      isMounted = false;
    };
  }, [setTheme, setLanguage]);

  // Compute initials for avatar fallback
  const computedInitials = (() => {
    const fn = firstName.trim();
    const ln = lastName.trim();
    if (fn && ln) return `${fn[0]}${ln[0]}`.toUpperCase();
    if (fn) return fn.slice(0, 2).toUpperCase();
    return "CA";
  })();

  // ── Handlers: Profile ─────────────────────────────────────────
  const handlePhotoChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.type.startsWith("image/")) {
      toast.error("Invalid file format", { description: "Please select a JPG or PNG image file." });
      return;
    }

    if (file.size > 5 * 1024 * 1024) {
      toast.error("File is too large", { description: "Maximum profile photo size is 5 MB." });
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const img = new Image();
      img.onload = () => {
        // Rescale & crop into a balanced 256x256 avatar canvas
        const canvas = document.createElement("canvas");
        const size = 256;
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext("2d");
        if (!ctx) return;

        const minDim = Math.min(img.width, img.height);
        const sx = (img.width - minDim) / 2;
        const sy = (img.height - minDim) / 2;

        ctx.drawImage(img, sx, sy, minDim, minDim, 0, 0, size, size);
        // Clean compressed JPEG (around 20-35 KB)
        const compressedDataUrl = canvas.toDataURL("image/jpeg", 0.85);

        setProfileImage(compressedDataUrl);
        toast.success("Photo selected", {
          description: "Click 'Save changes' to save your new photo.",
        });
      };
      img.src = reader.result as string;
    };
    reader.readAsDataURL(file);
  };

  const handleRemovePhoto = () => {
    setProfileImage(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
    toast.info("Photo removed", { description: "Click 'Save changes' to apply." });
  };

  const handleSaveProfile = async () => {
    if (!firstName.trim()) {
      toast.error("Validation error", { description: "First name cannot be empty." });
      return;
    }
    if (!email.trim() || !email.includes("@")) {
      toast.error("Validation error", { description: "Please enter a valid email address." });
      return;
    }

    try {
      setSavingProfile(true);
      const updated = await settingsService.updateProfile({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        membership_no: membershipNo.trim(),
        profile_image: profileImage,
      });

      // Update local storage and dispatch event to update AppLayout header immediately
      const full_name = updated.full_name;
      const userToStore = {
        full_name,
        email: updated.email,
        role: updated.role,
        profile_image: updated.profile_image,
      };
      localStorage.setItem("ca_user", JSON.stringify(userToStore));
      saveRecentAccount(full_name, updated.email, true);
      window.dispatchEvent(new Event("ca_user_updated"));

      toast.success("Profile updated successfully", {
        description: "Your personal details and photo have been saved.",
      });
    } catch (err: any) {
      const msg = err?.message || "Failed to update profile";
      toast.error("Update failed", { description: msg });
    } finally {
      setSavingProfile(false);
    }
  };

  // ── Handlers: Security ────────────────────────────────────────
  const handleToggle2FA = async (checked: boolean) => {
    setTwoFactor(checked);
    try {
      setUpdatingSecurity(true);
      await settingsService.updateSecurity({ two_factor_enabled: checked });
      toast.success(
        checked ? "Two-factor authentication enabled" : "Two-factor authentication disabled",
        { description: checked ? "Extra layer of security is now active." : "2FA has been disabled." }
      );
    } catch (err: any) {
      setTwoFactor(!checked);
      toast.error("Failed to update 2FA", { description: err?.message || "Please try again." });
    } finally {
      setUpdatingSecurity(false);
    }
  };

  const handleToggleLoginAlerts = async (checked: boolean) => {
    setLoginAlerts(checked);
    try {
      setUpdatingSecurity(true);
      await settingsService.updateSecurity({ login_alerts: checked });
      toast.success(
        checked ? "Login alerts enabled" : "Login alerts disabled",
        { description: checked ? "You will receive notifications for new sign-ins." : "Login alerts turned off." }
      );
    } catch (err: any) {
      setLoginAlerts(!checked);
      toast.error("Failed to update login alerts", { description: err?.message || "Please try again." });
    } finally {
      setUpdatingSecurity(false);
    }
  };

  const handleSessionTimeoutChange = async (val: string) => {
    const minutes = parseInt(val, 10);
    setSessionTimeout(minutes);
    try {
      setUpdatingSecurity(true);
      await settingsService.updateSecurity({ session_timeout_minutes: minutes });
      toast.success("Session timeout updated", {
        description: `Auto sign-out after ${minutes >= 60 ? `${minutes / 60} hour(s)` : `${minutes} min`} of inactivity.`,
      });
    } catch (err: any) {
      toast.error("Failed to update timeout", { description: err?.message || "Please try again." });
    } finally {
      setUpdatingSecurity(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPassword) {
      toast.error("Validation error", { description: "Please enter your current password." });
      return;
    }
    if (newPassword.length < 6) {
      toast.error("Weak password", { description: "New password must be at least 6 characters long." });
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Mismatch error", { description: "New passwords do not match." });
      return;
    }

    try {
      setChangingPassword(true);
      await settingsService.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });

      toast.success("Password changed successfully", {
        description: "Your account password has been updated.",
      });
      setPasswordDialogOpen(false);
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err: any) {
      toast.error("Change password failed", {
        description: err?.message || "Please check your current password and try again.",
      });
    } finally {
      setChangingPassword(false);
    }
  };

  // ── Handlers: Notifications ───────────────────────────────────
  const handleNotificationToggle = async (
    key: "compliance_deadlines" | "audit_alerts" | "client_activity" | "product_updates",
    value: boolean
  ) => {
    if (key === "compliance_deadlines") setComplianceDeadlines(value);
    if (key === "audit_alerts") setAuditAlerts(value);
    if (key === "client_activity") setClientActivity(value);
    if (key === "product_updates") setProductUpdates(value);

    try {
      await settingsService.updateNotifications({ [key]: value });
      toast.success("Preference saved", {
        description: `${key.replace(/_/g, " ")} ${value ? "enabled" : "disabled"}.`,
      });
    } catch (err: any) {
      // Revert on failure
      if (key === "compliance_deadlines") setComplianceDeadlines(!value);
      if (key === "audit_alerts") setAuditAlerts(!value);
      if (key === "client_activity") setClientActivity(!value);
      if (key === "product_updates") setProductUpdates(!value);
      toast.error("Failed to save preference", { description: err?.message });
    }
  };

  // ── Handlers: Preferences ─────────────────────────────────────
  const handleLanguageChange = async (val: string) => {
    const selectedLang = val as SupportedLanguage;
    setLanguage(selectedLang);
    try {
      await settingsService.updatePreferences({ language: selectedLang });
      const labels: Record<string, string> = {
        en: "English",
        hi: "हिन्दी (Hindi)",
        gu: "ગુજરાતી (Gujarati)",
        mr: "मराठी (Marathi)",
        ta: "தமிழ் (Tamil)",
      };
      toast.success("Language preference updated", {
        description: `Interface language switched to ${labels[val] || val}.`,
      });
    } catch (err: any) {
      toast.error("Failed to update language", { description: err?.message });
    }
  };

  const handleThemeChange = async (newTheme: "light" | "dark") => {
    setTheme(newTheme);
    try {
      await settingsService.updatePreferences({ theme: newTheme });
      toast.success("Theme updated", { description: `Appearance switched to ${newTheme} mode.` });
    } catch (err: any) {
      console.warn("Could not save theme preference to backend:", err);
    }
  };

  return (
    <>
      <PageHeader
        title={t("settings.title")}
        subtitle={t("settings.subtitle")}
      />

      <Tabs defaultValue="profile" className="gap-6">
        <TabsList className="flex-wrap">
          <TabsTrigger value="profile">
            <User className="size-4" /> {t("settings.tabs.profile")}
          </TabsTrigger>
          <TabsTrigger value="security">
            <Shield className="size-4" /> {t("settings.tabs.security")}
          </TabsTrigger>
          <TabsTrigger value="notifications">
            <Bell className="size-4" /> {t("settings.tabs.notifications")}
          </TabsTrigger>
          <TabsTrigger value="preferences">
            <Palette className="size-4" /> {t("settings.tabs.preferences")}
          </TabsTrigger>
        </TabsList>

        {/* ── Tab 1: Profile ────────────────────────────────────── */}
        <TabsContent value="profile">
          <Card>
            <CardHeader>
              <CardTitle>{t("profile.card_title")}</CardTitle>
              <CardDescription>{t("profile.card_desc")}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-4">
                <Avatar className="size-16 ring-2 ring-primary/20">
                  {profileImage && (
                    <AvatarImage src={profileImage} alt={`${firstName} ${lastName}`} />
                  )}
                  <AvatarFallback className="bg-primary text-primary-foreground text-lg font-semibold">
                    {computedInitials}
                  </AvatarFallback>
                </Avatar>

                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <input
                      type="file"
                      ref={fileInputRef}
                      accept="image/png,image/jpeg,image/jpg,image/webp"
                      onChange={handlePhotoChange}
                      className="hidden"
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => fileInputRef.current?.click()}
                      disabled={savingProfile}
                    >
                      {t("profile.change_photo")}
                    </Button>
                    {profileImage && (
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={handleRemovePhoto}
                        className="text-xs text-destructive hover:bg-destructive/10"
                        title="Remove photo"
                      >
                        <Trash2 className="size-3.5 mr-1" /> {t("profile.remove_photo")}
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">{t("profile.photo_helper")}</p>
                </div>
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="profile-first-name">{t("profile.first_name")}</Label>
                  <Input
                    id="profile-first-name"
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    placeholder="First name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-last-name">{t("profile.last_name")}</Label>
                  <Input
                    id="profile-last-name"
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    placeholder="Last name"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-email">{t("profile.email")}</Label>
                  <Input
                    id="profile-email"
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="name@firm.com"
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-membership">{t("profile.membership_no")}</Label>
                  <Input
                    id="profile-membership"
                    value={membershipNo}
                    onChange={(e) => setMembershipNo(e.target.value)}
                    placeholder="ICAI-123456"
                  />
                </div>
              </div>

              <Button onClick={handleSaveProfile} disabled={savingProfile}>
                {savingProfile ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" />
                    {t("profile.saving")}
                  </>
                ) : (
                  t("profile.save_changes")
                )}
              </Button>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 2: Security ───────────────────────────────────── */}
        <TabsContent value="security">
          <Card>
            <CardHeader>
              <CardTitle>{t("security.card_title")}</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <Row
                title={t("security.two_factor")}
                desc={t("security.two_factor_desc")}
              >
                <Switch
                  checked={twoFactor}
                  onCheckedChange={handleToggle2FA}
                  disabled={updatingSecurity}
                />
              </Row>

              <Row
                title={t("security.login_alerts")}
                desc={t("security.login_alerts_desc")}
              >
                <Switch
                  checked={loginAlerts}
                  onCheckedChange={handleToggleLoginAlerts}
                  disabled={updatingSecurity}
                />
              </Row>

              <Row
                title={t("security.session_timeout")}
                desc={t("security.session_timeout_desc")}
              >
                <Select
                  value={String(sessionTimeout)}
                  onValueChange={handleSessionTimeoutChange}
                  disabled={updatingSecurity}
                >
                  <SelectTrigger className="w-32">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="15">15 min</SelectItem>
                    <SelectItem value="30">30 min</SelectItem>
                    <SelectItem value="60">1 hour</SelectItem>
                    <SelectItem value="120">2 hours</SelectItem>
                  </SelectContent>
                </Select>
              </Row>

              <div className="pt-4">
                <Button
                  variant="outline"
                  onClick={() => setPasswordDialogOpen(true)}
                >
                  <Lock className="mr-2 size-4" /> {t("security.change_password")}
                </Button>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 3: Notifications ──────────────────────────────── */}
        <TabsContent value="notifications">
          <Card>
            <CardHeader>
              <CardTitle>{t("notifications.card_title")}</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <Row
                title={t("notifications.compliance")}
                desc={t("notifications.compliance_desc")}
              >
                <Switch
                  checked={complianceDeadlines}
                  onCheckedChange={(val) => handleNotificationToggle("compliance_deadlines", val)}
                />
              </Row>
              <Row
                title={t("notifications.audit")}
                desc={t("notifications.audit_desc")}
              >
                <Switch
                  checked={auditAlerts}
                  onCheckedChange={(val) => handleNotificationToggle("audit_alerts", val)}
                />
              </Row>
              <Row
                title={t("notifications.client")}
                desc={t("notifications.client_desc")}
              >
                <Switch
                  checked={clientActivity}
                  onCheckedChange={(val) => handleNotificationToggle("client_activity", val)}
                />
              </Row>
              <Row
                title={t("notifications.product")}
                desc={t("notifications.product_desc")}
              >
                <Switch
                  checked={productUpdates}
                  onCheckedChange={(val) => handleNotificationToggle("product_updates", val)}
                />
              </Row>
            </CardContent>
          </Card>
        </TabsContent>

        {/* ── Tab 4: Preferences ────────────────────────────────── */}
        <TabsContent value="preferences">
          <Card>
            <CardHeader>
              <CardTitle>{t("preferences.card_title")}</CardTitle>
            </CardHeader>
            <CardContent className="divide-y divide-border">
              <Row title={t("preferences.language")} desc={t("preferences.language_desc")}>
                <Select value={language} onValueChange={handleLanguageChange}>
                  <SelectTrigger className="w-44">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="en">English</SelectItem>
                    <SelectItem value="hi">हिन्दी (Hindi)</SelectItem>
                    <SelectItem value="gu">ગુજરાતી (Gujarati)</SelectItem>
                    <SelectItem value="mr">मराठी (Marathi)</SelectItem>
                    <SelectItem value="ta">தமிழ் (Tamil)</SelectItem>
                  </SelectContent>
                </Select>
              </Row>

              {/* Locked strictly to Indian Rupees (INR ₹) for Indian CA Practice */}
              <Row
                title={t("preferences.currency")}
                desc={t("preferences.currency_desc")}
              >
                <div className="flex items-center gap-2 rounded-lg border border-border bg-muted/40 px-3 py-2 text-sm font-medium">
                  <span className="font-bold text-primary">₹</span>
                  <span>INR ₹ (Indian Rupee)</span>
                  <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
                    India Only
                  </span>
                </div>
              </Row>

              <Row title={t("preferences.theme")} desc={t("preferences.theme_desc")}>
                <div className="flex items-center gap-2">
                  <Select value={theme} onValueChange={(t) => handleThemeChange(t as "light" | "dark")}>
                    <SelectTrigger className="w-40">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="dark">
                        <div className="flex items-center gap-2">
                          <Moon className="size-4 text-blue-400" />
                          <span>{t("preferences.theme_dark")}</span>
                        </div>
                      </SelectItem>
                      <SelectItem value="light">
                        <div className="flex items-center gap-2">
                          <Sun className="size-4 text-amber-500" />
                          <span>{t("preferences.theme_light")}</span>
                        </div>
                      </SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </Row>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>

      {/* ── Modal: Change Password ───────────────────────────────── */}
      <Dialog open={passwordDialogOpen} onOpenChange={setPasswordDialogOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t("security.change_password")}</DialogTitle>
            <DialogDescription>
              {t("security.change_password_desc")}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleChangePassword} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label htmlFor="current-password">{t("security.current_password")}</Label>
              <div className="relative">
                <Input
                  id="current-password"
                  type={showCurrentPassword ? "text" : "password"}
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  placeholder={t("security.enter_current")}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showCurrentPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="new-password">{t("security.new_password")}</Label>
              <div className="relative">
                <Input
                  id="new-password"
                  type={showNewPassword ? "text" : "password"}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  placeholder={t("security.min_chars")}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowNewPassword(!showNewPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showNewPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="confirm-password">{t("security.confirm_password")}</Label>
              <div className="relative">
                <Input
                  id="confirm-password"
                  type={showConfirmPassword ? "text" : "password"}
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder={t("security.reenter_new")}
                  required
                />
                <button
                  type="button"
                  onClick={() => setShowConfirmPassword(!showConfirmPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                >
                  {showConfirmPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                </button>
              </div>
              {newPassword && confirmPassword && newPassword !== confirmPassword && (
                <p className="text-xs text-destructive">{t("security.password_mismatch")}</p>
              )}
            </div>

            <DialogFooter className="pt-2">
              <Button
                type="button"
                variant="outline"
                onClick={() => setPasswordDialogOpen(false)}
                disabled={changingPassword}
              >
                {t("security.cancel")}
              </Button>
              <Button
                type="submit"
                disabled={changingPassword || (!!newPassword && !!confirmPassword && newPassword !== confirmPassword)}
              >
                {changingPassword ? (
                  <>
                    <Loader2 className="mr-2 size-4 animate-spin" /> {t("security.updating")}
                  </>
                ) : (
                  t("security.update_password")
                )}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
