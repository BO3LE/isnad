import { ApiError, type ValidationResult } from "./api";

// `POST /workflows/{id}/run` answers 422 with a ValidationResult in `detail` when the graph is not
// runnable (api/src/api/routers/workflows.py). The canvas shows those reasons in the validation
// panel instead of a toast, so the user gets the same list, in the server's words, either way.

function isIssueList(value: unknown): boolean {
  return (
    Array.isArray(value) &&
    value.every((issue) => typeof issue === "object" && issue !== null && typeof (issue as { message?: unknown }).message === "string")
  );
}

/** The refusal the server sent, or null when this error is not one. */
export function validationFrom(error: unknown): ValidationResult | null {
  if (!(error instanceof ApiError) || error.status !== 422) return null;
  const detail = (error.body as { detail?: unknown } | undefined)?.detail;
  if (typeof detail !== "object" || detail === null) return null;
  const { valid, issues } = detail as { valid?: unknown; issues?: unknown };
  if (typeof valid !== "boolean" || !isIssueList(issues)) return null;
  return detail as ValidationResult;
}
