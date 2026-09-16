import { useNavigate } from "react-router-dom";
import { Logo } from "@/components/app/Logo";
import { Button } from "@/design-system/components/Button";
import { EmptyState } from "@/design-system/components/EmptyState";
import { useAuth } from "@/lib/auth";

// P-11 (FRONTEND-PAGES-PLAN.md). Resources that aren't yours are "not found", never "forbidden",
// so another user's workflow is never revealed (DESIGN-SYSTEM.md §18.3).
export function NotFoundPage() {
  const navigate = useNavigate();
  const signedIn = Boolean(useAuth((state) => state.token));

  return (
    <div className="grid h-full place-items-center p-6">
      <div className="grid justify-items-center gap-6">
        <Logo className="text-text" />
        <EmptyState
          title="This page doesn't exist."
          body="The link may be wrong, or the item may have been deleted."
          actions={
            signedIn ? (
              <Button variant="primary" onClick={() => navigate("/workflows")}>
                Back to workflows
              </Button>
            ) : (
              <Button variant="primary" onClick={() => navigate("/login")}>
                Sign in
              </Button>
            )
          }
        />
      </div>
    </div>
  );
}

/** In-page version for a resource that doesn't exist or isn't yours. */
export function NotFoundState({ message, onBack }: { message: string; onBack?: () => void }) {
  const navigate = useNavigate();
  return (
    <EmptyState
      art={false}
      title={message}
      actions={
        <Button variant="primary" onClick={onBack ?? (() => navigate("/workflows"))}>
          Back to workflows
        </Button>
      }
    />
  );
}
