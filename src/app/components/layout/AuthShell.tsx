import { ReactNode } from "react";
import { ShieldCheck, Sparkles, TrendingUp } from "lucide-react";

export function AuthShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex min-h-screen w-full bg-background">
      {/* Brand panel */}
      <div className="relative hidden w-1/2 flex-col justify-between overflow-hidden border-r border-border/30 bg-gradient-to-br from-[#0b1120] via-[#0f172a] to-[#162032] p-8 lg:flex lg:p-14 text-white">
        {/* Subtle decorative background glow */}
        <div className="pointer-events-none absolute -left-24 -top-24 size-[28rem] rounded-full bg-primary/10 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-24 right-0 size-[28rem] rounded-full bg-blue-600/10 blur-3xl" />

        {/* Centered content container within the left column */}
        <div className="relative z-10 mx-auto flex h-full w-full max-w-lg flex-col justify-between">
          {/* Top Logo & App Title */}
          <div className="flex items-center gap-3">
            <div className="flex size-10 items-center justify-center rounded-xl bg-primary shadow-md shadow-primary/25">
              <span className="text-sm font-bold tracking-tight text-primary-foreground">CA</span>
            </div>
            <div>
              <span className="text-base font-semibold tracking-tight text-white">FinLedger AI</span>
              <p className="text-[11px] text-slate-400">Virtual Chartered Accountant</p>
            </div>
          </div>

          {/* Main Hero & Value Proposition */}
          <div className="my-auto py-10 space-y-8">
            <div className="space-y-3">
              <h2 className="text-3xl font-extrabold tracking-tight text-white lg:text-[2.25rem] leading-tight">
                The intelligent workspace for modern Chartered Accountants.
              </h2>
              <p className="text-sm lg:text-base text-slate-300 leading-relaxed">
                Accounting, GST, taxation, AI auditing and compliance — unified into one premium platform.
              </p>
            </div>

            {/* Feature Cards with Balanced Width */}
            <div className="space-y-3 pt-2">
              {[
                { icon: ShieldCheck, t: "AI-powered auditing", d: "Fraud & risk detection in seconds" },
                { icon: TrendingUp, t: "Real-time analytics", d: "Cash flow & financial health scores" },
                { icon: Sparkles, t: "AI assistant", d: "Tax, GST & compliance answers instantly" },
              ].map((f) => (
                <div
                  key={f.t}
                  className="flex items-center gap-3.5 rounded-xl bg-slate-800/40 p-3.5 ring-1 ring-white/10 backdrop-blur-sm transition-all hover:bg-slate-800/60 hover:ring-white/20"
                >
                  <div className="flex size-10 shrink-0 items-center justify-center rounded-lg bg-primary/20 text-primary">
                    <f.icon className="size-5 text-blue-400" />
                  </div>
                  <div className="leading-tight">
                    <p className="text-sm font-semibold text-white">{f.t}</p>
                    <p className="text-xs text-slate-400 mt-0.5">{f.d}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Bottom Copyright */}
          <p className="text-xs text-slate-500">
            © 2026 FinLedger AI · Designed for Indian Chartered Accounting practice
          </p>
        </div>
      </div>

      {/* Form panel with proportional centered card */}
      <div className="flex w-full flex-col items-center justify-center p-6 sm:p-12 lg:w-1/2">
        <div className="w-full max-w-[420px]">{children}</div>
      </div>
    </div>
  );
}
