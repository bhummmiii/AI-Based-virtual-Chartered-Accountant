import { useNavigate, Link } from "react-router-dom";
import { AuthShell } from "../components/layout/AuthShell";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Button } from "../components/ui/button";

export function Register() {
  const navigate = useNavigate();
  return (
    <AuthShell>
      <div className="space-y-2">
        <h1 className="text-2xl tracking-tight">Create your account</h1>
        <p className="text-muted-foreground text-sm">Start your 14-day free trial. No card required.</p>
      </div>
      <form
        className="mt-8 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          navigate("/otp");
        }}
      >
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-2">
            <Label htmlFor="fn">First name</Label>
            <Input id="fn" placeholder="Rahul" />
          </div>
          <div className="space-y-2">
            <Label htmlFor="ln">Last name</Label>
            <Input id="ln" placeholder="Khanna" />
          </div>
        </div>
        <div className="space-y-2">
          <Label htmlFor="email">Work email</Label>
          <Input id="email" type="email" placeholder="you@firm.com" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="firm">Firm / Practice name</Label>
          <Input id="firm" placeholder="Khanna & Associates" />
        </div>
        <div className="space-y-2">
          <Label htmlFor="pw">Password</Label>
          <Input id="pw" type="password" placeholder="Create a strong password" />
        </div>
        <Button type="submit" className="w-full">Create account</Button>
      </form>
      <p className="mt-8 text-center text-sm text-muted-foreground">
        Already registered? <Link to="/" className="text-primary hover:underline">Sign in</Link>
      </p>
    </AuthShell>
  );
}
