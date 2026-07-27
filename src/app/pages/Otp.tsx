import { useState } from "react";
import { useNavigate, Link } from "react-router";
import { ArrowLeft } from "lucide-react";
import { AuthShell } from "../components/layout/AuthShell";
import { Button } from "../components/ui/button";
import { InputOTP, InputOTPGroup, InputOTPSlot } from "../components/ui/input-otp";

export function Otp() {
  const navigate = useNavigate();
  const [value, setValue] = useState("");
  return (
    <AuthShell>
      <Link to="/" className="mb-6 inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground">
        <ArrowLeft className="size-4" /> Back
      </Link>
      <div className="space-y-2">
        <h1 className="text-2xl tracking-tight">Verify your identity</h1>
        <p className="text-muted-foreground text-sm">
          We sent a 6-digit code to your email. Enter it below to continue.
        </p>
      </div>
      <div className="mt-8 space-y-6">
        <InputOTP maxLength={6} value={value} onChange={setValue}>
          <InputOTPGroup className="w-full justify-between">
            {Array.from({ length: 6 }).map((_, i) => (
              <InputOTPSlot key={i} index={i} className="size-12 flex-1 text-lg" />
            ))}
          </InputOTPGroup>
        </InputOTP>
        <Button className="w-full" onClick={() => navigate("/app")}>Verify & continue</Button>
        <p className="text-center text-sm text-muted-foreground">
          Didn&apos;t get it? <button className="text-primary hover:underline">Resend code</button>
        </p>
      </div>
    </AuthShell>
  );
}
