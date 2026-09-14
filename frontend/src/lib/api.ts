// The frontend's only door to the backend. Types are generated from contracts/openapi.json
// (`npm run gen:api`) — never hand-written — so the frontend cannot drift from the API.
import type { components } from "./api-types";
import { useAuth } from "./auth";

type Schemas = components["schemas"];
export type WorkflowSummary = Schemas["WorkflowSummary"];
export type WorkflowOut = Schemas["WorkflowOut"];
export type WorkflowGraph = Schemas["WorkflowGraph"];
export type GraphNode = Schemas["GraphNode"];
export type AgentManifest = Schemas["AgentManifest"];
export type ValidationResult = Schemas["ValidationResult"];
export type RunState = Schemas["RunState"];
export type RunCreated = Schemas["RunCreated"];
export type NodeStatus = Schemas["NodeStatus"];
export type RunStatus = Schemas["RunStatus"];

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined) ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
    public body?: unknown,
  ) {
    super(message);
  }
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = useAuth.getState().token;
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  });
  if (response.status === 401) useAuth.getState().signOut();
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => undefined);
  if (!response.ok) {
    const detail = (body as { detail?: unknown } | undefined)?.detail;
    const message = typeof detail === "string" ? detail : "Something went wrong on our side. Try again.";
    throw new ApiError(response.status, message, body);
  }
  return body as T;
}

export const endpoints = {
  devLogin: (email: string) => api<Schemas["TokenResponse"]>("/auth/dev-login", { method: "POST", body: JSON.stringify({ email }) }),
  catalog: () => api<AgentManifest[]>("/agents/catalog"),
  workflows: () => api<WorkflowSummary[]>("/workflows"),
  workflow: (id: string) => api<WorkflowOut>(`/workflows/${id}`),
  createWorkflow: (name: string) => api<WorkflowOut>("/workflows", { method: "POST", body: JSON.stringify({ name }) }),
  saveWorkflow: (id: string, body: Schemas["WorkflowUpdate"]) =>
    api<WorkflowOut>(`/workflows/${id}`, { method: "PUT", body: JSON.stringify(body) }),
  validate: (id: string) => api<ValidationResult>(`/workflows/${id}/validate`, { method: "POST" }),
  run: (id: string) => api<RunCreated>(`/workflows/${id}/run`, { method: "POST" }),
  runState: (id: string) => api<RunState>(`/runs/${id}`),
  approve: (runId: string, nodeId: string, decision: "approve" | "reject", note?: string) =>
    api<RunCreated>(`/runs/${runId}/nodes/${nodeId}/approve`, { method: "POST", body: JSON.stringify({ decision, note }) }),
  cancel: (runId: string) => api<RunState>(`/runs/${runId}/cancel`, { method: "POST" }),
};
