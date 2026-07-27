import { ReactNode } from "react";
import { ShieldCheck, Sparkles, TrendingUp } from "lucide-react";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen w-full bg-background">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden bg-[#0f172a] p-12 text-white lg:flex">
        <div className="flex items-center gap-2.5">
          <div className="flex size-9 items-center justify-center rounded-xl bg-primary">
            <span className="text-sm tracking-tight">CA</span>
          </div>
          <span className="tracking-tight">FinLedger AI</span>
        </div>
        <div className="space-y-6">
          <h2 className="max-w-md text-3xl leading-tight tracking-tight text-white">
            The intelligent workspace for modern Chartered Accountants.
          </h2>
          <p className="max-w-md text-slate-300">
            Accounting, GST, taxation, AI auditing and compliance — unified into one premium platform.
          </p>
          <div className="grid max-w-md gap-3">
            {[
              { icon: ShieldCheck, t: "AI-powered auditing", d: "Fraud & risk detection in seconds" },
              { icon: TrendingUp, t: "Real-time analytics", d: "Cash flow & financial health scores" },
              { icon: Sparkles, t: "AI assistant", d: "Tax, GST & compliance answers instantly" },
            ].map((f) => (
              <div key={f.t} className="flex items-center gap-3 rounded-xl bg-white/5 p-3 ring-1 ring-white/10">
                <div className="flex size-9 items-center justify-center rounded-lg bg-primary/20 text-primary-foreground">
                  <f.icon className="size-4.5 text-blue-300" />
                </div>
                <div className="leading-tight">
                  <p className="text-sm text-white">{f.t}</p>
                  <p className="text-xs text-slate-400">{f.d}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
        <p className="text-xs text-slate-500">© 2026 FinLedger AI · Sample data for demonstration</p>
      </div>

      {/* Form panel */}
      <div className="flex w-full flex-col items-center justify-center p-6 lg:w-1/2">
        <div className="w-full max-w-sm">{children}</div>
      </div>
    </div>
  );
}
