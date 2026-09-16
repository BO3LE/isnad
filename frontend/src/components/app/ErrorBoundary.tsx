import { Component, type ErrorInfo, type ReactNode } from "react";
import { Button } from "@/design-system/components/Button";
import { EmptyState } from "@/design-system/components/EmptyState";

// DESIGN-SYSTEM.md §18.3 — "Something went wrong on our side" is allowed only for genuine crashes.
interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("Unhandled UI error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="grid h-full place-items-center">
        <EmptyState
          art={false}
          title="Something went wrong on our side."
          body="The page stopped responding. Reloading usually fixes it."
          actions={
            <>
              <Button variant="primary" onClick={() => window.location.reload()}>
                Reload the page
              </Button>
              <Button onClick={() => this.setState({ error: null })}>Try again</Button>
            </>
          }
        />
      </div>
    );
  }
}
