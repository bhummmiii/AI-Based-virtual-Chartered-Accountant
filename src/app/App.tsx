import { BrowserRouter, Routes, Route, Navigate } from "react-router";
import { Toaster } from "./components/ui/sonner";
import { AppProvider } from "./context/AppContext";
import { AppLayout } from "./components/layout/AppLayout";
import { Login } from "./pages/Login";
import { Register } from "./pages/Register";
import { Forgot } from "./pages/Forgot";
import { Otp } from "./pages/Otp";
import { Dashboard } from "./pages/Dashboard";
import { Workspace } from "./pages/Workspace";
import { ClientWorkspace } from "./pages/ClientWorkspace";
import { Assistant } from "./pages/Assistant";
import { GovRules } from "./pages/GovRules";
import { Reports } from "./pages/Reports";
import { Settings } from "./pages/Settings";

export default function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Login />} />
          <Route path="/register" element={<Register />} />
          <Route path="/forgot" element={<Forgot />} />
          <Route path="/otp" element={<Otp />} />
          <Route path="/app" element={<AppLayout />}>
            <Route index element={<Dashboard />} />
            <Route path="workspace" element={<Workspace />} />
            <Route path="workspace/:clientId" element={<ClientWorkspace />} />
            <Route path="assistant" element={<Assistant />} />
            <Route path="updates" element={<GovRules />} />
            <Route path="reports" element={<Reports />} />
            <Route path="settings" element={<Settings />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
      <Toaster richColors position="top-right" />
    </AppProvider>
  );
}
