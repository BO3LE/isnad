import { lazy, Suspense, type ReactNode } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { ErrorBoundary } from "./components/app/ErrorBoundary";
import { Spinner } from "./design-system/components/Progress";
import { ToastProvider } from "./design-system/components/Toast";
import { useAuth } from "./lib/auth";
import { CanvasPage } from "./pages/CanvasPage";
import { LoginPage } from "./pages/LoginPage";
import { NotFoundPage } from "./pages/NotFoundPage";
import { RegisterPage } from "./pages/RegisterPage";
import { LogsPage } from "@/pages/LogsPage";
import { OutputsPage } from "@/pages/OutputsPage";
import { RunPage } from "./pages/RunPage";
import { WorkflowsPage } from "./pages/WorkflowsPage";

// Routes follow FRONTEND-PAGES-PLAN.md §3. Pages still to build: P-05 run history,
// P-07 approval, P-10 connections.
const DevDesignPage = lazy(() => import("./pages/DevDesignPage").then((m) => ({ default: m.DevDesignPage })));

export function App() {
  return (
    <ErrorBoundary>
      <ToastProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/register" element={<RegisterPage />} />
            <Route path="/" element={<Navigate to="/workflows" replace />} />
            <Route
              path="/workflows"
              element={
                <RequireAuth>
                  <WorkflowsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/workflows/:workflowId"
              element={
                <RequireAuth>
                  <CanvasPage />
                </RequireAuth>
              }
            />
            <Route
              path="/runs/:runId/logs"
              element={
                <RequireAuth>
                  <LogsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/runs/:runId/outputs"
              element={
                <RequireAuth>
                  <OutputsPage />
                </RequireAuth>
              }
            />
            <Route
              path="/runs/:runId"
              element={
                <RequireAuth>
                  <RunPage />
                </RequireAuth>
              }
            />
            {import.meta.env.DEV && (
              <Route
                path="/dev/design"
                element={
                  <Suspense fallback={<Spinner label="Loading the design system" />}>
                    <DevDesignPage />
                  </Suspense>
                }
              />
            )}
            <Route path="*" element={<NotFoundPage />} />
          </Routes>
        </BrowserRouter>
      </ToastProvider>
    </ErrorBoundary>
  );
}

function RequireAuth({ children }: { children: ReactNode }) {
  const token = useAuth((state) => state.token);
  const hydrated = useAuth((state) => state.hydrated);
  const location = useLocation();
  // In Supabase mode the stored session loads asynchronously; redirecting before it resolves
  // would bounce a signed-in user to /login on every page refresh.
  if (!hydrated) return <Spinner label="Loading your session" />;
  if (!token) return <Navigate to={`/login?next=${encodeURIComponent(location.pathname)}`} replace />;
  return <>{children}</>;
}
