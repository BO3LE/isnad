import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useToast } from "@/design-system/components/toast-context";
import { ApiError, endpoints, type Connection } from "@/lib/api";
import { connectGoogle, connectProblem } from "@/lib/connections";

export const CONNECTIONS_KEY = ["connections"] as const;

/**
 * "Connect Google", with the waiting state it needs: Google's screen is in another window, which
 * this tab can't watch, so the person can cancel the wait (see `lib/connections.ts`). On success
 * the connections are fetched again and `onConnected` gets the account that is new or renewed.
 */
export function useConnectGoogle(onConnected?: (connection: Connection | undefined) => void) {
  const client = useQueryClient();
  const toast = useToast();
  const [waiting, setWaiting] = useState(false);
  const abort = useRef<AbortController | null>(null);

  useEffect(() => () => abort.current?.abort(), []);

  const connect = useCallback(async () => {
    abort.current?.abort();
    const controller = new AbortController();
    abort.current = controller;
    const before = client.getQueryData<Connection[]>(CONNECTIONS_KEY) ?? [];
    setWaiting(true);
    try {
      const result = await connectGoogle(controller.signal);
      if (result.ok) {
        const after = await client.fetchQuery({ queryKey: CONNECTIONS_KEY, queryFn: endpoints.connections, staleTime: 0 });
        const known = new Set(before.map((c) => c.id));
        // A reconnect keeps its id (api: same account → same row), so fall back to the newest one.
        const fresh = after.find((c) => !known.has(c.id)) ?? [...after].sort((a, b) => b.created_at.localeCompare(a.created_at))[0];
        toast({ variant: "success", message: fresh ? `Connected ${fresh.account_email}.` : "Google connected." });
        onConnected?.(fresh);
      } else {
        const problem = connectProblem(result.reason);
        if (problem) toast({ variant: "error", message: problem });
      }
    } catch (error) {
      toast({
        variant: "error",
        message: error instanceof ApiError && error.status === 503 ? error.message : "Couldn't start connecting Google. Try again.",
      });
    } finally {
      if (abort.current === controller) abort.current = null;
      setWaiting(false);
    }
  }, [client, onConnected, toast]);

  const cancel = useCallback(() => abort.current?.abort(), []);
  return { connect, cancel, waiting };
}
