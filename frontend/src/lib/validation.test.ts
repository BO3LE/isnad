import { describe, expect, it } from "vitest";
import { ApiError } from "./api";
import { validationFrom } from "./validation";

const refusal = (issues: unknown) => new ApiError(422, "", { detail: { valid: false, issues } });

describe("validationFrom", () => {
  it("reads the reasons the run endpoint refused with", () => {
    const issues = [{ code: "orphan_node", message: "Researcher isn't connected to anything.", severity: "error", node_id: "r" }];
    expect(validationFrom(refusal(issues))).toEqual({ valid: false, issues });
  });

  it("keeps an empty refusal, which is still a refusal", () => {
    expect(validationFrom(refusal([]))).toEqual({ valid: false, issues: [] });
  });

  it("ignores an error that is not the server refusing a graph", () => {
    expect(validationFrom(new ApiError(503, "Job queue unavailable"))).toBeNull();
    expect(validationFrom(new ApiError(422, "", { detail: "Not a validation result" }))).toBeNull();
    expect(validationFrom(new ApiError(422, "", { detail: { valid: false } }))).toBeNull();
    expect(validationFrom(new ApiError(422, "", { detail: { valid: false, issues: [{ code: "x" }] } }))).toBeNull();
    expect(validationFrom(new Error("offline"))).toBeNull();
    expect(validationFrom(undefined)).toBeNull();
  });
});
