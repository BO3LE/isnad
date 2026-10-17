import { useEffect, useState } from "react";
import { Button } from "@/design-system/components/Button";
import { Dialog } from "@/design-system/components/Dialog";
import { Segmented } from "@/design-system/components/Segmented";
import type { ConnectionAccess } from "@/lib/api";
import { ACCESS, ACCESS_ORDER, SECURITY } from "@/lib/connections";

// What Isnad will ask Google for, said before anyone is sent there (S-09). Google won't grant
// YouTube together with Drive, so the person picks one; the other is a second connect.

export interface ConnectGoogleDialogProps {
  /** Which access to offer first; `null` keeps the dialog closed. */
  initial: ConnectionAccess | null;
  onClose: () => void;
  onContinue: (access: ConnectionAccess) => void;
}

export function ConnectGoogleDialog({ initial, onClose, onContinue }: ConnectGoogleDialogProps) {
  const [access, setAccess] = useState<ConnectionAccess>(initial ?? "youtube");
  useEffect(() => {
    if (initial) setAccess(initial);
  }, [initial]);

  return (
    <Dialog
      open={initial !== null}
      onClose={onClose}
      title="Connect Google"
      description="Google connects YouTube on its own, apart from Drive and Gmail. Choose one now; you can connect the other to the same account afterwards."
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" onClick={() => onContinue(access)}>
            Continue to Google
          </Button>
        </>
      }
    >
      <div className="grid gap-3">
        <Segmented
          label="What Isnad may do"
          options={ACCESS_ORDER.map((value) => ({ value, label: ACCESS[value].label }))}
          value={access}
          onChange={setAccess}
        />
        <p className="text-body-sm text-text">{ACCESS[access].does}</p>
        <p className="text-body-sm text-text-muted">You choose the account, and can untick anything on Google's screen. {SECURITY}</p>
      </div>
    </Dialog>
  );
}
