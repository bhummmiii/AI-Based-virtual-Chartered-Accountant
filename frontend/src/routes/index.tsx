// ============================================================
// Application Routes Configuration
// ============================================================

import { Routes, Route } from "react-router-dom";

// Route path constants — keep in sync with constants/routes.ts
const AppRoutes = () => {
  return (
    <Routes>
      {/* TODO: Add route definitions during implementation */}
      <Route path="/" element={<div>Dashboard</div>} />
    </Routes>
  );
};

export default AppRoutes;
