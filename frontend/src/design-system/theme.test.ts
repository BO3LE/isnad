import { applyTheme, resolveTheme } from "./theme";

function mockPrefersDark(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
}

describe("theme", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.documentElement.removeAttribute("data-theme");
  });

  it("resolves an explicit choice regardless of the OS", () => {
    mockPrefersDark(true);
    expect(resolveTheme("light")).toBe("light");
    mockPrefersDark(false);
    expect(resolveTheme("dark")).toBe("dark");
  });

  it("resolves system from prefers-color-scheme", () => {
    mockPrefersDark(true);
    expect(resolveTheme("system")).toBe("dark");
    mockPrefersDark(false);
    expect(resolveTheme("system")).toBe("light");
  });

  // tokens.css carries the dark palette on [data-theme="dark"] only, so "system" has to be
  // resolved to a concrete value here — leaving the attribute off would paint light on a dark OS.
  it("always stamps a concrete theme, never 'system'", () => {
    mockPrefersDark(true);
    applyTheme("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");

    mockPrefersDark(false);
    applyTheme("system");
    expect(document.documentElement.getAttribute("data-theme")).toBe("light");

    applyTheme("dark");
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  });
});
