import { User, Shield, Bell, Globe, Palette, KeyRound, Copy } from "lucide-react";
import { PageHeader } from "../components/common/PageHeader";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Switch } from "../components/ui/switch";
import { Avatar, AvatarFallback } from "../components/ui/avatar";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { Separator } from "../components/ui/separator";

function Row({ title, desc, children }: { title: string; desc: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <div><p className="text-sm">{title}</p><p className="text-xs text-muted-foreground">{desc}</p></div>
      {children}
    </div>
  );
}

export function Settings() {
  return (
    <>
      <PageHeader title="Settings" subtitle="Manage your profile, security and preferences" />

      <Tabs defaultValue="profile" className="gap-6">
        <TabsList className="flex-wrap">
          <TabsTrigger value="profile"><User className="size-4" /> Profile</TabsTrigger>
          <TabsTrigger value="security"><Shield className="size-4" /> Security</TabsTrigger>
          <TabsTrigger value="notifications"><Bell className="size-4" /> Notifications</TabsTrigger>
          <TabsTrigger value="preferences"><Palette className="size-4" /> Preferences</TabsTrigger>
          <TabsTrigger value="api"><KeyRound className="size-4" /> API Keys</TabsTrigger>
        </TabsList>

        <TabsContent value="profile">
          <Card>
            <CardHeader><CardTitle>Profile</CardTitle><CardDescription>Update your personal information</CardDescription></CardHeader>
            <CardContent className="space-y-5">
              <div className="flex items-center gap-4">
                <Avatar className="size-16"><AvatarFallback className="bg-primary text-primary-foreground text-lg">RK</AvatarFallback></Avatar>
                <div className="space-y-1">
                  <Button variant="outline" size="sm">Change photo</Button>
                  <p className="text-xs text-muted-foreground">JPG or PNG, max 2 MB</p>
                </div>
              </div>
              <div className="grid gap-4 sm:grid-cols-2">
                <div className="space-y-2"><Label>First name</Label><Input defaultValue="Rahul" /></div>
                <div className="space-y-2"><Label>Last name</Label><Input defaultValue="Khanna" /></div>
                <div className="space-y-2"><Label>Email</Label><Input defaultValue="rahul@finledger.ai" /></div>
                <div className="space-y-2"><Label>Membership No.</Label><Input defaultValue="ICAI-123456" /></div>
              </div>
              <Button>Save changes</Button>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="security">
          <Card>
            <CardHeader><CardTitle>Security</CardTitle></CardHeader>
            <CardContent className="divide-y divide-border">
              <Row title="Two-factor authentication" desc="Add an extra layer of security"><Switch defaultChecked /></Row>
              <Row title="Login alerts" desc="Get notified of new sign-ins"><Switch defaultChecked /></Row>
              <Row title="Session timeout" desc="Auto sign-out after inactivity">
                <Select defaultValue="30"><SelectTrigger className="w-32"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="15">15 min</SelectItem><SelectItem value="30">30 min</SelectItem><SelectItem value="60">1 hour</SelectItem></SelectContent></Select>
              </Row>
              <div className="pt-4"><Button variant="outline">Change password</Button></div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="notifications">
          <Card>
            <CardHeader><CardTitle>Notification Preferences</CardTitle></CardHeader>
            <CardContent className="divide-y divide-border">
              <Row title="Compliance deadlines" desc="GST & tax filing reminders"><Switch defaultChecked /></Row>
              <Row title="Audit alerts" desc="Fraud & risk notifications"><Switch defaultChecked /></Row>
              <Row title="Client activity" desc="Uploads & status changes"><Switch /></Row>
              <Row title="Product updates" desc="New features & tips"><Switch defaultChecked /></Row>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="preferences">
          <Card>
            <CardHeader><CardTitle>Preferences</CardTitle></CardHeader>
            <CardContent className="divide-y divide-border">
              <Row title="Language" desc="Interface language">
                <Select defaultValue="en"><SelectTrigger className="w-40"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="en">English</SelectItem><SelectItem value="hi">Hindi</SelectItem><SelectItem value="ta">Tamil</SelectItem></SelectContent></Select>
              </Row>
              <Row title="Currency" desc="Default display currency">
                <Select defaultValue="inr"><SelectTrigger className="w-40"><SelectValue /></SelectTrigger><SelectContent><SelectItem value="inr">INR ₹</SelectItem><SelectItem value="usd">USD $</SelectItem></SelectContent></Select>
              </Row>
              <Row title="Theme" desc="Appearance"><div className="flex items-center gap-2 text-sm text-muted-foreground"><Globe className="size-4" /> Light</div></Row>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="api">
          <Card>
            <CardHeader><CardTitle>API Keys</CardTitle><CardDescription>Use these keys to integrate FinLedger AI with your systems</CardDescription></CardHeader>
            <CardContent className="space-y-4">
              <div className="space-y-2">
                <Label>Live API key</Label>
                <div className="flex gap-2">
                  <Input readOnly value="fl_live_YOUR_API_KEY_HERE" className="font-mono" />
                  <Button variant="outline" size="icon"><Copy className="size-4" /></Button>
                </div>
                <p className="text-xs text-muted-foreground">Replace with your real key. Never expose live keys in client code.</p>
              </div>
              <Separator />
              <Button variant="outline">Generate new key</Button>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </>
  );
}
