import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mail, Lock, Eye, EyeOff, User, AlertCircle, CheckCircle2, ArrowRight } from "lucide-react";
import { toast } from "sonner";
import { AuthShell } from "../components/layout/AuthShell";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { Checkbox } from "../components/ui/checkbox";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "../components/ui/dialog";
import { authService, getRecentAccounts, isAccountRemembered, type RecentAccount } from "../services/auth.service";

// ── Validation regex & helpers ─────────────────────────────────
// Matches valid email format e.g. Mahendrapawar@gmail.com
export const EMAIL_REGEX = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

export function validateEmail(email: string): string | null {
  if (!email || !email.trim()) {
    return "Email address is required";
  }
  if (!EMAIL_REGEX.test(email.trim())) {
    return "Please enter a valid email format (e.g. Mahendrapawar@gmail.com)";
  }
  return null;
}

export function validatePassword(password: string, isRegister = false): string | null {
  if (!password) {
    return "Password is required";
  }
  if (password.length < 6) {
    return "Password must be at least 6 characters";
  }
  if (isRegister && password.length < 8) {
    return "Password must be at least 8 characters for account security";
  }
  return null;
}

// ── Colored Brand Icons ────────────────────────────────────────
function GoogleIcon({ className = "size-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24">
      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.06H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.94l2.85-2.22.81-.63z" />
      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.06l3.66 2.84c.87-2.6 3.3-4.52 6.16-4.52z" />
    </svg>
  );
}

function MicrosoftIcon({ className = "size-4" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 23 23">
      <path fill="#f35325" d="M1 1h10v10H1z" />
      <path fill="#81bc06" d="M12 1h10v10H12z" />
      <path fill="#05a6f0" d="M1 12h10v10H1z" />
      <path fill="#ffba08" d="M12 12h10v10H12z" />
    </svg>
  );
}

interface LoginProps {
  initialMode?: "login" | "register";
}

export function Login({ initialMode = "login" }: LoginProps) {
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">(initialMode);

  // ── Password visibility ──
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [loading, setLoading] = useState(false);

  // ── Sign In Form state ── (Empty by default with clean placeholders)
  const [loginEmail, setLoginEmail] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [loginErrors, setLoginErrors] = useState<{ email?: string; password?: string }>({});

  // ── Register Form state ── (Empty by default with clean placeholders)
  const [regName, setRegName] = useState("");
  const [regEmail, setRegEmail] = useState("");
  const [regPassword, setRegPassword] = useState("");
  const [regConfirmPassword, setRegConfirmPassword] = useState("");
  const [regErrors, setRegErrors] = useState<{
    name?: string;
    email?: string;
    password?: string;
    confirmPassword?: string;
  }>({});

  // ── Google OAuth Modal state ──
  const [googleModalOpen, setGoogleModalOpen] = useState(false);
  const [googleStep, setGoogleStep] = useState<"account" | "password">("account");
  const [selectedGoogleAccount, setSelectedGoogleAccount] = useState<{
    email: string;
    name?: string;
  } | null>(null);
  const [googlePassword, setGooglePassword] = useState("");
  const [showGooglePassword, setShowGooglePassword] = useState(false);
  const [googlePasswordError, setGooglePasswordError] = useState("");
  const [googleCustomEmail, setGoogleCustomEmail] = useState("");
  const [googleCustomName, setGoogleCustomName] = useState("");
  const [googleCustomError, setGoogleCustomError] = useState("");
  const [googleLoading, setGoogleLoading] = useState(false);
  const [recentAccounts, setRecentAccounts] = useState(getRecentAccounts());

  // ── Validation trigger helpers ──
  const validateLoginForm = () => {
    const errors: { email?: string; password?: string } = {};
    const emailErr = validateEmail(loginEmail);
    if (emailErr) errors.email = emailErr;
    const passErr = validatePassword(loginPassword, false);
    if (passErr) errors.password = passErr;
    setLoginErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const validateRegisterForm = () => {
    const errors: {
      name?: string;
      email?: string;
      password?: string;
      confirmPassword?: string;
    } = {};

    if (!regName.trim() || regName.trim().length < 2) {
      errors.name = "Full name is required (min 2 characters)";
    }

    const emailErr = validateEmail(regEmail);
    if (emailErr) errors.email = emailErr;

    const passErr = validatePassword(regPassword, true);
    if (passErr) errors.password = passErr;

    if (!regConfirmPassword) {
      errors.confirmPassword = "Confirm password is required";
    } else if (regPassword !== regConfirmPassword) {
      errors.confirmPassword = "Passwords do not match";
    }

    setRegErrors(errors);
    return Object.keys(errors).length === 0;
  };

  // ── Sign In Submission ──
  const handleLoginSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateLoginForm()) {
      toast.error("Validation error", {
        description: "Please resolve the highlighted errors before submitting.",
      });
      return;
    }

    setLoading(true);
    try {
      await authService.login({ email: loginEmail.trim(), password: loginPassword });
      toast.success("Signed in successfully", {
        description: `Welcome back to FinLedger AI.`,
      });
      navigate("/app");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Sign in failed";
      toast.error("Sign in failed", { description: msg });
    } finally {
      setLoading(false);
    }
  };

  // ── Create Account Submission ──
  const handleRegisterSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validateRegisterForm()) {
      toast.error("Validation error", {
        description: "Please resolve the highlighted errors before submitting.",
      });
      return;
    }

    setLoading(true);
    try {
      await authService.register({
        name: regName.trim(),
        email: regEmail.trim(),
        password: regPassword,
        role: "ca",
      });
      toast.success("Account created successfully!", {
        description: `Welcome to FinLedger AI, ${regName.trim()}.`,
      });
      navigate("/app");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Registration failed";
      toast.error("Create account failed", { description: msg });
    } finally {
      setLoading(false);
    }
  };

  // ── Direct Login for Already Remembered Google Accounts (No password asked again) ──
  const handleDirectGoogleLogin = async (email: string, name?: string) => {
    setGoogleLoading(true);
    try {
      const res = await authService.googleAuth({
        email: email.trim(),
        name: name || email.trim().split("@")[0],
      });
      setGoogleModalOpen(false);
      setGoogleStep("account");
      setSelectedGoogleAccount(null);
      setGooglePassword("");
      toast.success("Signed in with Google", {
        description: `Welcome back, ${res.user?.full_name || email}.`,
      });
      navigate("/app");
    } catch (err: unknown) {
      // If direct login requires credentials, fallback to password step
      handleSelectAccountForPassword(email, name);
    } finally {
      setGoogleLoading(false);
    }
  };

  // ── Handler for Account Card Click in Google Modal ──
  const handleAccountCardClick = (acc: RecentAccount) => {
    // If account has already signed in before with password, don't ask again!
    if (acc.hasPasswordSet || isAccountRemembered(acc.email)) {
      handleDirectGoogleLogin(acc.email, acc.name);
    } else {
      // First time signup with Google: ask for password
      handleSelectAccountForPassword(acc.email, acc.name);
    }
  };

  // ── Handler for Custom Google Email Form ──
  const handleCustomEmailContinue = () => {
    const emailErr = validateEmail(googleCustomEmail);
    if (emailErr) {
      setGoogleCustomError(emailErr);
      return;
    }
    setGoogleCustomError("");

    // If account has already signed in before with password, don't ask again!
    if (isAccountRemembered(googleCustomEmail.trim())) {
      handleDirectGoogleLogin(
        googleCustomEmail.trim(),
        googleCustomName.trim() || undefined
      );
    } else {
      // First time signup with Google: ask for password
      handleSelectAccountForPassword(
        googleCustomEmail.trim(),
        googleCustomName.trim() || undefined
      );
    }
  };

  // ── Step 1 -> Step 2: User selects or enters Google email, proceed to Password ──
  const handleSelectAccountForPassword = (email: string, name?: string) => {
    const emailErr = validateEmail(email);
    if (emailErr) {
      setGoogleCustomError(emailErr);
      return;
    }
    setGoogleCustomError("");
    setSelectedGoogleAccount({
      email: email.trim(),
      name: name || email.trim().split("@")[0],
    });
    setGooglePassword("");
    setGooglePasswordError("");
    setShowGooglePassword(false);
    setGoogleStep("password");
  };

  // ── Step 2: Submit password & authenticate with Google ──
  const handleGooglePasswordSubmit = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!selectedGoogleAccount) return;

    if (!googlePassword) {
      setGooglePasswordError("Password is required");
      return;
    }
    if (googlePassword.length < 6) {
      setGooglePasswordError("Password must be at least 6 characters");
      return;
    }

    setGooglePasswordError("");
    setGoogleLoading(true);

    try {
      const res = await authService.googleAuth({
        email: selectedGoogleAccount.email,
        name: selectedGoogleAccount.name,
        password: googlePassword,
      });
      setGoogleModalOpen(false);
      setGoogleStep("account");
      setSelectedGoogleAccount(null);
      setGooglePassword("");
      toast.success("Signed in with Google", {
        description: `Authenticated as ${res.user?.full_name || selectedGoogleAccount.email}.`,
      });
      navigate("/app");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Google authentication failed";
      setGooglePasswordError(msg);
      toast.error("Google sign in failed", { description: msg });
    } finally {
      setGoogleLoading(false);
    }
  };

  return (
    <AuthShell>
      {/* ── Workspace Badge & Title ── */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="inline-flex items-center gap-1.5 rounded-full bg-primary/10 px-3 py-1 text-xs font-semibold text-primary border border-primary/20">
            Chartered Accountant Workspace
          </span>
        </div>
        <h1 className="text-2xl font-bold tracking-tight text-foreground">
          {mode === "login" ? "Welcome back" : "Create your account"}
        </h1>
        <p className="text-sm text-muted-foreground">
          {mode === "login"
            ? "Sign in to your FinLedger AI workspace."
            : "Register your practice account for AI audits, GST and compliance."}
        </p>
      </div>

      {/* ── Beautiful Balanced Segmented Switcher (Sign in / Create account) ── */}
      <div className="mt-5 grid grid-cols-2 rounded-xl border border-border/80 bg-secondary/60 p-1">
        <button
          type="button"
          onClick={() => {
            setMode("login");
            setLoginErrors({});
          }}
          className={`flex items-center justify-center rounded-lg py-2.5 text-sm font-semibold transition-all ${
            mode === "login"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-secondary/80"
          }`}
        >
          Sign in
        </button>
        <button
          type="button"
          onClick={() => {
            setMode("register");
            setRegErrors({});
          }}
          className={`flex items-center justify-center rounded-lg py-2.5 text-sm font-semibold transition-all ${
            mode === "register"
              ? "bg-primary text-primary-foreground shadow-sm"
              : "text-muted-foreground hover:text-foreground hover:bg-secondary/80"
          }`}
        >
          Create account
        </button>
      </div>

      {/* ── Mode: SIGN IN FORM ── */}
      {mode === "login" ? (
        <form className="mt-6 space-y-4" onSubmit={handleLoginSubmit} noValidate>
          {/* Email Field */}
          <div className="space-y-1.5">
            <Label htmlFor="login-email">Email</Label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="login-email"
                type="email"
                value={loginEmail}
                onChange={(e) => {
                  setLoginEmail(e.target.value);
                  if (loginErrors.email) setLoginErrors((p) => ({ ...p, email: undefined }));
                }}
                onBlur={() => {
                  const err = validateEmail(loginEmail);
                  if (err) setLoginErrors((p) => ({ ...p, email: err }));
                }}
                className={`pl-9 ${
                  loginErrors.email ? "border-destructive focus-visible:ring-destructive" : ""
                }`}
                placeholder="Mahendrapawar@gmail.com"
              />
            </div>
            {loginErrors.email && (
              <p className="flex items-center gap-1.5 text-xs text-destructive animate-in fade-in-50">
                <AlertCircle className="size-3.5 shrink-0" />
                {loginErrors.email}
              </p>
            )}
          </div>

          {/* Password Field */}
          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="login-password">Password</Label>
              <Link to="/forgot" className="text-xs text-primary hover:underline">
                Forgot password?
              </Link>
            </div>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="login-password"
                type={showPassword ? "text" : "password"}
                value={loginPassword}
                onChange={(e) => {
                  setLoginPassword(e.target.value);
                  if (loginErrors.password) setLoginErrors((p) => ({ ...p, password: undefined }));
                }}
                onBlur={() => {
                  const err = validatePassword(loginPassword, false);
                  if (err) setLoginErrors((p) => ({ ...p, password: err }));
                }}
                className={`px-9 ${
                  loginErrors.password ? "border-destructive focus-visible:ring-destructive" : ""
                }`}
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            {loginErrors.password && (
              <p className="flex items-center gap-1.5 text-xs text-destructive animate-in fade-in-50">
                <AlertCircle className="size-3.5 shrink-0" />
                {loginErrors.password}
              </p>
            )}
          </div>

          <label className="flex items-center gap-2 text-sm text-muted-foreground cursor-pointer">
            <Checkbox defaultChecked /> Keep me signed in
          </label>

          <Button type="submit" className="w-full" disabled={loading}>
            {loading ? "Signing in…" : "Sign in"}
          </Button>
        </form>
      ) : (
        /* ── Mode: CREATE ACCOUNT FORM ── */
        <form className="mt-6 space-y-4" onSubmit={handleRegisterSubmit} noValidate>
          {/* Full Name Field */}
          <div className="space-y-1.5">
            <Label htmlFor="reg-name">Full Name</Label>
            <div className="relative">
              <User className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="reg-name"
                type="text"
                value={regName}
                onChange={(e) => {
                  setRegName(e.target.value);
                  if (regErrors.name) setRegErrors((p) => ({ ...p, name: undefined }));
                }}
                onBlur={() => {
                  if (!regName.trim() || regName.trim().length < 2) {
                    setRegErrors((p) => ({ ...p, name: "Full name must be at least 2 characters" }));
                  }
                }}
                className={`pl-9 ${
                  regErrors.name ? "border-destructive focus-visible:ring-destructive" : ""
                }`}
                placeholder="Mahendra Pawar"
              />
            </div>
            {regErrors.name && (
              <p className="flex items-center gap-1.5 text-xs text-destructive animate-in fade-in-50">
                <AlertCircle className="size-3.5 shrink-0" />
                {regErrors.name}
              </p>
            )}
          </div>

          {/* Email Field with explicit format validation */}
          <div className="space-y-1.5">
            <Label htmlFor="reg-email">Email Address</Label>
            <div className="relative">
              <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="reg-email"
                type="email"
                value={regEmail}
                onChange={(e) => {
                  setRegEmail(e.target.value);
                  if (regErrors.email) setRegErrors((p) => ({ ...p, email: undefined }));
                }}
                onBlur={() => {
                  const err = validateEmail(regEmail);
                  if (err) setRegErrors((p) => ({ ...p, email: err }));
                }}
                className={`pl-9 ${
                  regErrors.email ? "border-destructive focus-visible:ring-destructive" : ""
                }`}
                placeholder="Mahendrapawar@gmail.com"
              />
            </div>
            {regErrors.email ? (
              <p className="flex items-center gap-1.5 text-xs text-destructive animate-in fade-in-50">
                <AlertCircle className="size-3.5 shrink-0" />
                {regErrors.email}
              </p>
            ) : (
              <p className="text-[11px] text-muted-foreground">
                Example format: <code className="text-primary font-medium">Mahendrapawar@gmail.com</code>
              </p>
            )}
          </div>

          {/* Password Field */}
          <div className="space-y-1.5">
            <Label htmlFor="reg-password">Password</Label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="reg-password"
                type={showPassword ? "text" : "password"}
                value={regPassword}
                onChange={(e) => {
                  setRegPassword(e.target.value);
                  if (regErrors.password) setRegErrors((p) => ({ ...p, password: undefined }));
                }}
                onBlur={() => {
                  const err = validatePassword(regPassword, true);
                  if (err) setRegErrors((p) => ({ ...p, password: err }));
                }}
                className={`px-9 ${
                  regErrors.password ? "border-destructive focus-visible:ring-destructive" : ""
                }`}
                placeholder="Create password (min 8 characters)"
              />
              <button
                type="button"
                onClick={() => setShowPassword((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            {regErrors.password && (
              <p className="flex items-center gap-1.5 text-xs text-destructive animate-in fade-in-50">
                <AlertCircle className="size-3.5 shrink-0" />
                {regErrors.password}
              </p>
            )}
          </div>

          {/* Confirm Password Field */}
          <div className="space-y-1.5">
            <Label htmlFor="reg-confirm-password">Confirm Password</Label>
            <div className="relative">
              <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                id="reg-confirm-password"
                type={showConfirmPassword ? "text" : "password"}
                value={regConfirmPassword}
                onChange={(e) => {
                  setRegConfirmPassword(e.target.value);
                  if (regErrors.confirmPassword) {
                    setRegErrors((p) => ({ ...p, confirmPassword: undefined }));
                  }
                }}
                onBlur={() => {
                  if (regPassword !== regConfirmPassword) {
                    setRegErrors((p) => ({ ...p, confirmPassword: "Passwords do not match" }));
                  }
                }}
                className={`px-9 ${
                  regErrors.confirmPassword ? "border-destructive focus-visible:ring-destructive" : ""
                }`}
                placeholder="Re-enter password"
              />
              <button
                type="button"
                onClick={() => setShowConfirmPassword((s) => !s)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                {showConfirmPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
            {regErrors.confirmPassword && (
              <p className="flex items-center gap-1.5 text-xs text-destructive animate-in fade-in-50">
                <AlertCircle className="size-3.5 shrink-0" />
                {regErrors.confirmPassword}
              </p>
            )}
          </div>

          <Button type="submit" className="w-full mt-2" disabled={loading}>
            {loading ? "Creating account…" : "Create account"}
          </Button>
        </form>
      )}

      {/* ── Divider ── */}
      <div className="my-5 flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" /> or continue with <span className="h-px flex-1 bg-border" />
      </div>

      {/* ── Social OAuth Buttons ── */}
      <div className="grid grid-cols-2 gap-3">
        <Button
          variant="outline"
          type="button"
          className="gap-2 font-medium hover:bg-secondary/60 hover:border-primary/40 transition-all"
          onClick={() => {
            setRecentAccounts(getRecentAccounts());
            setGoogleStep("account");
            setSelectedGoogleAccount(null);
            setGooglePassword("");
            setGooglePasswordError("");
            setGoogleCustomError("");
            setGoogleModalOpen(true);
          }}
        >
          <GoogleIcon className="size-4" />
          Google
        </Button>
        <Button
          variant="outline"
          type="button"
          className="gap-2 font-medium hover:bg-secondary/60 transition-all"
          onClick={() => {
            if (loginEmail && validateEmail(loginEmail) === null) {
              handleSelectAccountForPassword(loginEmail, loginEmail.split("@")[0]);
              setGoogleModalOpen(true);
            } else {
              setRecentAccounts(getRecentAccounts());
              setGoogleStep("account");
              setSelectedGoogleAccount(null);
              setGooglePassword("");
              setGooglePasswordError("");
              setGoogleCustomError("");
              setGoogleModalOpen(true);
            }
          }}
        >
          <MicrosoftIcon className="size-4" />
          Microsoft
        </Button>
      </div>

      {/* ── Footer Toggle Link ── */}
      <p className="mt-7 text-center text-sm text-muted-foreground">
        {mode === "login" ? (
          <>
            Don&apos;t have an account?{" "}
            <button
              type="button"
              onClick={() => {
                setMode("register");
                setRegErrors({});
              }}
              className="font-medium text-primary hover:underline"
            >
              Create one
            </button>
          </>
        ) : (
          <>
            Already registered?{" "}
            <button
              type="button"
              onClick={() => {
                setMode("login");
                setLoginErrors({});
              }}
              className="font-medium text-primary hover:underline"
            >
              Sign in
            </button>
          </>
        )}
      </p>

      {/* ── Google Account Selector & Password Authentication Modal ── */}
      <Dialog
        open={googleModalOpen}
        onOpenChange={(open) => {
          setGoogleModalOpen(open);
          if (!open) {
            setGoogleStep("account");
            setSelectedGoogleAccount(null);
            setGooglePassword("");
            setGooglePasswordError("");
            setGoogleCustomError("");
          }
        }}
      >
        <DialogContent className="sm:max-w-md">
          <DialogHeader className="items-center text-center space-y-2 pb-2 border-b border-border/60">
            <div className="flex size-12 items-center justify-center rounded-2xl bg-secondary/80 shadow-sm">
              <GoogleIcon className="size-6" />
            </div>
            <DialogTitle className="text-lg font-semibold">
              {googleStep === "account" ? "Sign in with Google" : "Welcome"}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {googleStep === "account" ? (
                <>
                  Choose an account to continue to <strong className="text-foreground">FinLedger AI</strong>
                </>
              ) : (
                <div className="mt-1 flex items-center justify-center">
                  <div className="inline-flex items-center gap-2 rounded-full border border-border/80 bg-secondary/60 px-3 py-1 text-xs">
                    <span className="flex size-4 items-center justify-center rounded-full bg-primary/20 text-[10px] font-bold text-primary">
                      {selectedGoogleAccount?.name ? selectedGoogleAccount.name[0].toUpperCase() : "G"}
                    </span>
                    <span className="font-medium text-foreground">{selectedGoogleAccount?.email}</span>
                    <button
                      type="button"
                      onClick={() => {
                        setGoogleStep("account");
                        setGooglePassword("");
                        setGooglePasswordError("");
                      }}
                      className="ml-1 text-[11px] font-medium text-primary hover:underline"
                    >
                      Change
                    </button>
                  </div>
                </div>
              )}
            </DialogDescription>
          </DialogHeader>

          {googleStep === "account" ? (
            /* ── Step 1: Account Selection ── */
            <div className="space-y-3 py-3">
              {/* Dynamic recent accounts */}
              {recentAccounts.map((acc, idx) => (
                <button
                  key={acc.email + idx}
                  type="button"
                  disabled={googleLoading}
                  onClick={() => handleAccountCardClick(acc)}
                  className="flex w-full items-center justify-between gap-3 rounded-xl border border-border p-3.5 text-left transition-all hover:border-primary/50 hover:bg-secondary/40 group"
                >
                  <div className="flex items-center gap-3">
                    <div className="flex size-10 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-sm">
                      {acc.name ? acc.name[0].toUpperCase() : acc.email[0].toUpperCase()}
                    </div>
                    <div>
                      <p className="text-sm font-medium text-foreground group-hover:text-primary transition-colors">
                        {acc.name}
                      </p>
                      <p className="text-xs text-muted-foreground">{acc.email}</p>
                    </div>
                  </div>
                  <ArrowRight className="size-4 text-muted-foreground group-hover:text-primary transition-colors" />
                </button>
              ))}

              {/* Custom Google Email Input option */}
              <div className="rounded-xl border border-dashed border-border/80 p-3.5 bg-muted/20 space-y-2.5">
                <p className="text-xs font-medium text-muted-foreground">Or connect with another Google account:</p>
                <div className="space-y-1.5">
                  <Input
                    type="email"
                    value={googleCustomEmail}
                    onChange={(e) => {
                      setGoogleCustomEmail(e.target.value);
                      if (googleCustomError) setGoogleCustomError("");
                    }}
                    placeholder="e.g. anushka@gmail.com"
                    className={`text-xs ${
                      googleCustomError ? "border-destructive focus-visible:ring-destructive" : ""
                    }`}
                  />
                  {googleCustomError && (
                    <p className="flex items-center gap-1 text-[11px] text-destructive">
                      <AlertCircle className="size-3 shrink-0" />
                      {googleCustomError}
                    </p>
                  )}
                </div>
                <Button
                  size="sm"
                  className="w-full gap-2 text-xs font-medium"
                  disabled={googleLoading || !googleCustomEmail.trim()}
                  onClick={handleCustomEmailContinue}
                >
                  Continue with Google
                  <ArrowRight className="size-3.5" />
                </Button>
              </div>
            </div>
          ) : (
            /* ── Step 2: Password Verification ── */
            <form onSubmit={handleGooglePasswordSubmit} className="space-y-4 py-3" noValidate>
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="google-pass-input">Enter your password</Label>
                  <span className="text-xs text-muted-foreground">Google verification</span>
                </div>
                <div className="relative">
                  <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
                  <Input
                    id="google-pass-input"
                    type={showGooglePassword ? "text" : "password"}
                    autoFocus
                    value={googlePassword}
                    onChange={(e) => {
                      setGooglePassword(e.target.value);
                      if (googlePasswordError) setGooglePasswordError("");
                    }}
                    className={`px-9 ${
                      googlePasswordError ? "border-destructive focus-visible:ring-destructive" : ""
                    }`}
                    placeholder="Enter your account password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowGooglePassword((s) => !s)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                  >
                    {showGooglePassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                  </button>
                </div>
                {googlePasswordError && (
                  <p className="flex items-center gap-1.5 text-xs text-destructive animate-in fade-in-50">
                    <AlertCircle className="size-3.5 shrink-0" />
                    {googlePasswordError}
                  </p>
                )}
              </div>

              <div className="flex items-center justify-between pt-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={googleLoading}
                  onClick={() => {
                    setGoogleStep("account");
                    setGooglePassword("");
                    setGooglePasswordError("");
                  }}
                >
                  Back
                </Button>
                <Button
                  type="submit"
                  size="sm"
                  disabled={googleLoading || !googlePassword.trim()}
                  className="gap-2"
                >
                  {googleLoading ? "Signing in…" : "Next"}
                  <ArrowRight className="size-3.5" />
                </Button>
              </div>
            </form>
          )}

          <div className="border-t border-border/50 pt-2 text-center text-[11px] text-muted-foreground">
            FinLedger AI uses Google Account authentication to securely verify your identity.
          </div>
        </DialogContent>
      </Dialog>
    </AuthShell>
  );
}
