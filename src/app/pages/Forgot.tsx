import { useNavigate, Link } from "react-router";
import { ArrowLeft, Mail } from "lucide-react";
import { AuthShell } from "../components/layout/AuthShell";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";

export function Forgot() {
  const navigate = useNavigate();
  return (
    <AuthShell>
      <Link to="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Back to sign in
      </Link>
      <div className="space-y-2">
        <h1 className="text-2xl tracking-tight">Reset your password</h1>
        <p className="text-muted-foreground text-sm">
          Enter your email and we&apos;ll send a verification code.
        </p>
      </div>
      <form
        className="mt-8 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          navigate("/otp");
        }}
      >
        <div className="space-y-2">
          <Label htmlFor="email">Email</Label>
          <div className="relative">
            <Mail className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input id="email" type="email" placeholder="you@firm.com" className="pl-9" />
          </div>
        </div>
        <Button type="submit" className="w-full">Send code</Button>
      </form>
    </AuthShell>
  );
}
