import { useState } from "react";
import { Link, useNavigate } from "react-router";
import { Mail, Lock, Eye, EyeOff } from "lucide-react";
import { AuthShell } from "../components/layout/AuthShell";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";
import { Checkbox } from "../components/ui/checkbox";

export function Login() {
  const navigate = useNavigate();
  const [show, setShow] = useState(false);

  return (
    <AuthShell>
      <div className="space-y-2">
        <h1 className="text-2xl tracking-tight">Welcome back</h1>
        <p className="text-muted-foreground text-sm">Sign in to your FinLedger AI workspace.</p>
      </div>

      <form
        className="mt-8 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          navigate("/app");
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input id="email" type="email" defaultValue="rahul@finledger.ai" className="pl-9" placeholder="you@firm.com" />
          </div>
        </div>
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <Label htmlFor="password">Password</Label>
            <Link to="/forgot" className="text-xs text-primary hover:underline">Forgot password?</Link>
          </div>
          <div className="relative">
            <Lock className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input id="password" type={show ? "text" : "password"} defaultValue="password" className="px-9" />
            <button
              type="button"
              onClick={() => setShow((s) => !s)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
            >
              {show ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
            </button>
          </div>
        </div>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Checkbox defaultChecked /> Keep me signed in
        </label>
        <Button type="submit" className="w-full">Sign in</Button>
      </form>

      <div className="my-6 flex items-center gap-3 text-xs text-muted-foreground">
        <span className="h-px flex-1 bg-border" /> or continue with <span className="h-px flex-1 bg-border" />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Button variant="outline" onClick={() => navigate("/app")}>Google</Button>
        <Button variant="outline" onClick={() => navigate("/app")}>Microsoft</Button>
      </div>

      <p className="mt-8 text-center text-sm text-muted-foreground">
        Don&apos;t have an account?{" "}
        <Link to="/register" className="text-primary hover:underline">Create one</Link>
      </p>
    </AuthShell>
  );
}
