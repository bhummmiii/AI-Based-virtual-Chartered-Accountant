// ============================================================
// Application Routes Configuration
// ============================================================

import { Routes, Route, Navigate } from "react-router-dom";
import { ClientWorkspace } from "../components/client/components/ClientWorkspace";

const AppRoutes = () => {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/clients" replace />} />
      {/* Client workspace — main document management UI */}
      <Route path="/clients/:clientId/workspace" element={<ClientWorkspace />} />
      {/* Fallback */}
      <Route path="*" element={<div style={{ padding: "2rem", color: "#94a3b8" }}>Page not found</div>} />
    </Routes>
  );
};

export default AppRoutes;
