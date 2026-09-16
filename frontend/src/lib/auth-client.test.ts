import { ApiError } from "./api";
import { authErrorMessage, meetsPasswordRules } from "./auth-client";

describe("authErrorMessage", () => {
  // §21 S-01: the message must never reveal which of the two was wrong.
  it("gives the same message for a bad email and a bad password", () => {
    expect(authErrorMessage(new ApiError(401, "No user with that email"))).toBe("That email and password don't match.");
    expect(authErrorMessage(new ApiError(400, "Password incorrect"))).toBe("That email and password don't match.");
  });

  it("has its own message for rate limiting", () => {
    expect(authErrorMessage(new ApiError(429, "slow down"))).toBe("Too many attempts. Try again in a minute.");
  });

  it("explains a dead network rather than blaming the credentials", () => {
    expect(authErrorMessage(new TypeError("Failed to fetch"))).toMatch(/couldn't reach the server/i);
  });

  it("passes a server message through", () => {
    expect(authErrorMessage(new ApiError(500, "Database is down."))).toBe("Database is down.");
  });
});

describe("meetsPasswordRules", () => {
  it("needs at least 8 characters", () => {
    expect(meetsPasswordRules("short")).toBe(false);
    expect(meetsPasswordRules("12345678")).toBe(true);
  });
});
