import type { ReactNode } from "react";
import { BrowserRouter, Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useAuth } from "./lib/auth";
import { CanvasPage } from "./pages/CanvasPage";
import { LoginPage } from "./pages/LoginPage";
import { RunPage } from "./pages/RunPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";

// Routes follow DESIGN-SYSTEM.md §19. Screens still to build: approval, logs, outputs, connections.
export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/" element={<Navigate to="/workflows" replace />} />
        <Route path="/workflows" element={<Protected><WorkflowsPage /></Protected>} />
        <Route path="/workflows/:workflowId" element={<Protected><CanvasPage /></Protected>} />
        <Route path="/runs/:runId" element={<Protected><RunPage /></Protected>} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}

function Protected({ children }: { children: ReactNode }) {
  const token = useAuth((s) => s.token);
  const location = useLocation();
  if (!token) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  return <>{children}</>;
}

function NotFound() {
  return (
    <main className="grid h-full place-items-center p-8 text-center">
      <div className="grid gap-3">
        <h1 className="text-heading-lg">This page doesn&apos;t exist.</h1>
        <Link className="text-interactive hover:underline" to="/workflows">
          Back to workflows
        </Link>
      </div>
    </main>
  );
}
